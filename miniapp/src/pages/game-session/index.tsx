import { Button, Image, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchCurrentPrescriptionData } from '../../demo/patientAppData'
import { isDemoSession } from '../../demo/session'
import type { CurrentPrescription } from '../../types/patientApp'
import { todayLocalDate } from '../../utils/date'
import {
  createColorSequenceRound,
  evaluateColorSequenceAttempt,
  type ColorSequenceRound,
  type ColorToken,
} from './colorSequence'
import { createCategorySwitchRound, evaluateCategorySwitchAttempt, type CategoryRule, type CategorySwitchRound } from './categorySwitch'
import { createGameIntroSteps } from './gameIntro'
import { GAME_CATALOG, gameCodeForActionSource } from '../../game/catalog'
import {
  GAME_AUDIO_TEXT,
  isGameAudioMuted,
  playAudioSrc,
  playGameAudio,
  playGameFeedback,
  setGameAudioMuted,
  SOUND_DISCRIMINATION_AUDIO,
  stopActiveGameAudio,
  type GameAudioKey,
} from './gameAudio'
import type { GameActionSummary, GameCode, GameDifficulty, GameEndReason, GameTrainingPayload } from './gameTypes'
import { createInhibitionRound, evaluateInhibitionAttempt, type InhibitionRound } from './inhibition'
import {
  createPatternSequenceRound,
  evaluatePatternSequenceAttempt,
  type PatternSequenceRound,
  type PatternToken,
} from './patternSequence'
import {
  createPuzzleRound,
  evaluatePuzzleCompletion,
  puzzleTileImageStyle,
  swapPuzzleTiles,
  type PuzzleRound,
  type PuzzleTile,
} from './puzzle'
import {
  postGameTrainingRecord,
  savePendingGameUploadAfterActiveRetry,
  startPendingGameUploadRetryLoop,
  type TrainingRecordUploadError,
} from './retryUpload'
import { buildGameTrainingResult } from './scoring'
import {
  createSoundDiscriminationRound,
  evaluateSoundDiscriminationAttempt,
  markCardPreviewed,
  nextSoundPreviewCard,
  type SoundCard,
  type SoundDiscriminationRound,
} from './soundDiscrimination'

type PrescriptionAction = NonNullable<CurrentPrescription>['actions'][number]

type SessionPhase = 'loading' | 'setup' | 'intro' | 'playing' | 'paused' | 'result'

type UnitResult = {
  correct: boolean
  detail?: Record<string, unknown>
}

type UploadState =
  | 'idle'
  | 'demo_local'
  | 'uploading'
  | 'uploaded'
  | 'upload_rejected'
  | 'pending_retry'
  | 'blocked_by_existing_pending'
  | 'upload_save_failed'

const DIFFICULTY_OPTIONS: GameDifficulty[] = ['简单', '中等', '困难']

const COLOR_LABEL: Record<ColorToken, string> = {
  blue: '蓝',
  green: '绿',
  yellow: '黄',
  red: '红',
  teal: '青',
}

const SOUND_CATEGORY_LABEL: Record<SoundCard['category'], string> = {
  bird: '小鸟',
  train: '火车',
  phone: '电话',
  laugh: '笑声',
  drum: '鼓声',
}

function normalizeDifficulty(value: string): GameDifficulty {
  return DIFFICULTY_OPTIONS.includes(value as GameDifficulty) ? (value as GameDifficulty) : '简单'
}

function suggestedDurationMinutes(action: GameActionSummary): number {
  return action.duration_minutes && action.duration_minutes > 0 ? action.duration_minutes : 10
}

function textForEndReason(reason: GameEndReason): string {
  return reason === 'timer' ? '已按运动计划建议时长完成' : '已提前结束，本次记录为部分完成'
}

function formatNumber(value: number | null | undefined, fallback = '-'): string {
  return value === null || value === undefined || !Number.isFinite(value) ? fallback : String(value)
}

function formatClock(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds))
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const seconds = safeSeconds % 60
  return [hours, minutes, seconds].map((item) => String(item).padStart(2, '0')).join(':')
}

function uploadStateText(uploadState: UploadState): string {
  if (uploadState === 'demo_local') return '本次演示不保存'
  if (uploadState === 'uploading') return '正在上传'
  if (uploadState === 'uploaded') return '已上传'
  if (uploadState === 'upload_rejected') return '上传失败'
  if (uploadState === 'pending_retry') return '待补传'
  if (uploadState === 'blocked_by_existing_pending') return '未保存，已有旧记录待补传'
  if (uploadState === 'upload_save_failed') return '未保存'
  return '等待上传'
}

function feedbackKind(correct: boolean): 'correct' | 'wrong' {
  return correct ? 'correct' : 'wrong'
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export default function GameSessionPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
  const demoMode = isDemoSession()
  const [phase, setPhase] = useState<SessionPhase>('loading')
  const [prescription, setPrescription] = useState<CurrentPrescription>(null)
  const [loaded, setLoaded] = useState(false)
  const [difficultyIndex, setDifficultyIndex] = useState(0)
  const [difficultyReason, setDifficultyReason] = useState('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [unitResults, setUnitResults] = useState<UnitResult[]>([])
  const [feedback, setFeedback] = useState('')
  const [muted, setMuted] = useState(isGameAudioMuted())
  const [uploadState, setUploadState] = useState<UploadState>('idle')
  const [resultPayload, setResultPayload] = useState<GameTrainingPayload | null>(null)
  const [error, setError] = useState('')
  const [introText, setIntroText] = useState('')
  const [activeColorRound, setActiveColorRound] = useState<ColorSequenceRound | null>(null)
  const [activeColorInput, setActiveColorInput] = useState<ColorToken[]>([])
  const [colorRevealing, setColorRevealing] = useState(false)
  const [activeInhibitionRound, setActiveInhibitionRound] = useState<InhibitionRound | null>(null)
  const [activePatternRound, setActivePatternRound] = useState<PatternSequenceRound | null>(null)
  const [activePatternInput, setActivePatternInput] = useState<string[]>([])
  const [patternRevealing, setPatternRevealing] = useState(false)
  const [activeCategoryRound, setActiveCategoryRound] = useState<CategorySwitchRound | null>(null)
  const [activeSoundRound, setActiveSoundRound] = useState<SoundDiscriminationRound | null>(null)
  const [soundPhase, setSoundPhase] = useState<'preview' | 'choose'>('preview')
  const [soundPreviewingCardId, setSoundPreviewingCardId] = useState<string | null>(null)
  const [soundPlaybackError, setSoundPlaybackError] = useState('')
  const [activePuzzleRound, setActivePuzzleRound] = useState<PuzzleRound | null>(null)
  const [selectedPuzzleTileId, setSelectedPuzzleTileId] = useState<string | null>(null)
  const [puzzlePreviewing, setPuzzlePreviewing] = useState(false)
  const activeColorInputRef = useRef<ColorToken[]>([])
  const activeColorRoundRef = useRef<ColorSequenceRound | null>(null)
  const activePatternInputRef = useRef<string[]>([])
  const activePatternRoundRef = useRef<PatternSequenceRound | null>(null)
  const activeCategoryRoundRef = useRef<CategorySwitchRound | null>(null)
  const activeSoundRoundRef = useRef<SoundDiscriminationRound | null>(null)
  const activePuzzleRoundRef = useRef<PuzzleRound | null>(null)
  const soundPhaseRef = useRef<'preview' | 'choose'>('preview')
  const soundRoundRunIdRef = useRef(0)
  const soundPreviewInFlightRef = useRef(false)
  const targetSecondsRef = useRef(600)
  const elapsedSecondsRef = useRef(0)
  const unitResultsRef = useRef<UnitResult[]>([])
  const phaseRef = useRef<SessionPhase>('loading')
  const actionRef = useRef<GameActionSummary | null>(null)
  const gameCodeRef = useRef<GameCode | null>(null)
  const difficultyRef = useRef<GameDifficulty>('简单')
  const difficultyReasonRef = useRef('')
  const endStartedRef = useRef(false)
  const unitLockedRef = useRef(false)
  const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const revealTimerDeadlineRef = useRef<number | null>(null)
  const revealTimerRemainingMsRef = useRef<number | null>(null)
  const roundTimeoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const roundTimeoutDeadlineRef = useRef<number | null>(null)
  const roundTimeoutRemainingMsRef = useRef<number | null>(null)
  const nextRoundTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingNextRoundRef = useRef(false)
  const previousCategoryRuleRef = useRef<CategoryRule | undefined>(undefined)
  const roundStartedAtRef = useRef(Date.now())
  const initializedRef = useRef(false)
  const loadingPrescriptionRef = useRef(false)
  const loadedRef = useRef(false)
  const introRunIdRef = useRef(0)

  const action = useMemo<PrescriptionAction | null>(() => {
    return prescription?.actions.find((item) => item.id === actionId) ?? null
  }, [actionId, prescription])
  const actionIsGame = action?.internal_type === 'game'
  const gameCode = action ? gameCodeForActionSource(action.source_key) : null
  const difficulty = DIFFICULTY_OPTIONS[difficultyIndex] ?? '简单'
  const prescribedDifficulty = normalizeDifficulty(action?.difficulty ?? '')
  const adjustedDifficulty = difficulty !== prescribedDifficulty
  const remainingSeconds = Math.max(0, targetSecondsRef.current - elapsedSeconds)

  function setSessionPhase(nextPhase: SessionPhase) {
    phaseRef.current = nextPhase
    setPhase(nextPhase)
  }

  function setSoundRoundPhase(nextPhase: 'preview' | 'choose') {
    soundPhaseRef.current = nextPhase
    setSoundPhase(nextPhase)
  }

  function showAttemptFeedback(correct: boolean) {
    const feedbackClip = playGameFeedback(feedbackKind(correct))
    setFeedback(feedbackClip.text)
  }

  function currentSoundRoundPhase(): 'preview' | 'choose' {
    return soundPhaseRef.current
  }

  function clearRoundTimers(options: { preserveRevealRemaining?: boolean; preserveRoundTimeoutRemaining?: boolean } = {}) {
    if (revealTimerRef.current) {
      clearTimeout(revealTimerRef.current)
      revealTimerRef.current = null
    }
    revealTimerDeadlineRef.current = null
    if (!options.preserveRevealRemaining) {
      revealTimerRemainingMsRef.current = null
    }
    if (roundTimeoutTimerRef.current) {
      clearTimeout(roundTimeoutTimerRef.current)
      roundTimeoutTimerRef.current = null
    }
    roundTimeoutDeadlineRef.current = null
    if (!options.preserveRoundTimeoutRemaining) {
      roundTimeoutRemainingMsRef.current = null
    }
    if (nextRoundTimerRef.current) {
      clearTimeout(nextRoundTimerRef.current)
      nextRoundTimerRef.current = null
    }
  }

  function resetSessionState() {
    clearRoundTimers()
    elapsedSecondsRef.current = 0
    unitResultsRef.current = []
    endStartedRef.current = false
    unitLockedRef.current = false
    pendingNextRoundRef.current = false
    activeColorInputRef.current = []
    activeColorRoundRef.current = null
    activePatternInputRef.current = []
    activePatternRoundRef.current = null
    activeCategoryRoundRef.current = null
    activeSoundRoundRef.current = null
    activePuzzleRoundRef.current = null
    soundPhaseRef.current = 'preview'
    soundRoundRunIdRef.current += 1
    soundPreviewInFlightRef.current = false
    previousCategoryRuleRef.current = undefined
    roundStartedAtRef.current = Date.now()
    introRunIdRef.current += 1
    setElapsedSeconds(0)
    setUnitResults([])
    setFeedback('')
    setIntroText('')
    setUploadState('idle')
    setResultPayload(null)
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setActiveInhibitionRound(null)
    setActivePatternRound(null)
    setActivePatternInput([])
    setPatternRevealing(false)
    setActiveCategoryRound(null)
    setActiveSoundRound(null)
    setSoundRoundPhase('preview')
    setSoundPreviewingCardId(null)
    setSoundPlaybackError('')
    setActivePuzzleRound(null)
    setSelectedPuzzleTileId(null)
    setPuzzlePreviewing(false)
  }

  useDidShow(() => {
    setMuted(isGameAudioMuted())
    if (phaseRef.current === 'intro' || phaseRef.current === 'playing' || phaseRef.current === 'paused' || phaseRef.current === 'result') {
      return
    }
    if (initializedRef.current || loadedRef.current || loadingPrescriptionRef.current) return

    initializedRef.current = true
    loadingPrescriptionRef.current = true
    setLoaded(false)
    loadedRef.current = false
    setPrescription(null)
    setSessionPhase('loading')
    setError('')
    setDifficultyReason('')
    resetSessionState()

    fetchCurrentPrescriptionData()
      .then((body) => {
        const nextAction = body?.actions.find((item) => item.id === actionId)
        setPrescription(body)
        if (nextAction?.internal_type === 'game') {
          const defaultDifficulty = normalizeDifficulty(nextAction.difficulty)
          setDifficultyIndex(DIFFICULTY_OPTIONS.indexOf(defaultDifficulty))
          targetSecondsRef.current = suggestedDurationMinutes(nextAction) * 60
        }
        loadedRef.current = true
        setLoaded(true)
        setSessionPhase('setup')
      })
      .catch((err) => {
        setPrescription(null)
        setError(err instanceof Error ? err.message : '加载失败')
        loadedRef.current = true
        setLoaded(true)
        setSessionPhase('setup')
      })
      .finally(() => {
        loadingPrescriptionRef.current = false
      })
  })

  useDidHide(() => {
    stopActiveGameAudio()
  })

  useEffect(() => {
    phaseRef.current = phase
  }, [phase])

  useEffect(() => {
    loadedRef.current = loaded
  }, [loaded])

  useEffect(() => {
    elapsedSecondsRef.current = elapsedSeconds
  }, [elapsedSeconds])

  useEffect(() => {
    unitResultsRef.current = unitResults
  }, [unitResults])

  useEffect(() => {
    actionRef.current = actionIsGame ? action : null
    if (actionIsGame && action) {
      targetSecondsRef.current = suggestedDurationMinutes(action) * 60
    }
  }, [action, actionIsGame])

  useEffect(() => {
    gameCodeRef.current = gameCode
  }, [gameCode])

  useEffect(() => {
    difficultyRef.current = difficulty
  }, [difficulty])

  useEffect(() => {
    difficultyReasonRef.current = difficultyReason
  }, [difficultyReason])

  useEffect(() => {
    if (phase !== 'playing') return undefined

    const timer = setInterval(() => {
      if (endStartedRef.current || phaseRef.current !== 'playing') return
      const nextElapsedSeconds = elapsedSecondsRef.current + 1
      elapsedSecondsRef.current = nextElapsedSeconds
      setElapsedSeconds(nextElapsedSeconds)
      if (nextElapsedSeconds >= targetSecondsRef.current) {
        endSession('timer', targetSecondsRef.current)
      }
    }, 1000)

    return () => clearInterval(timer)
  }, [phase])

  useEffect(() => {
    if (phase !== 'playing') return
    if (endStartedRef.current) return
    if (gameCode === 'game-memory-color-sequence' && !activeColorRound) {
      startColorRound()
    }
    if (gameCode === 'game-memory-pattern-sequence' && !activePatternRound) {
      startPatternRound()
    }
    if (gameCode === 'game-executive-inhibition' && !activeInhibitionRound) {
      startInhibitionRound()
    }
    if (gameCode === 'game-executive-category-switch' && !activeCategoryRound) {
      startCategoryRound()
    }
    if (gameCode === 'game-audiovisual-sound-discrimination' && !activeSoundRound) {
      startSoundRound()
    }
    if (gameCode === 'game-audiovisual-puzzle' && !activePuzzleRound) {
      startPuzzleRound()
    }
  }, [activeCategoryRound, activeColorRound, activeInhibitionRound, activePatternRound, activePuzzleRound, activeSoundRound, gameCode, phase])

  useEffect(() => {
    return () => {
      introRunIdRef.current += 1
      clearRoundTimers()
      stopActiveGameAudio()
    }
  }, [])

  function canContinueRoundTimers(): boolean {
    return phaseRef.current === 'playing' && !endStartedRef.current && elapsedSecondsRef.current < targetSecondsRef.current
  }

  function handleRoundTimeout() {
    roundTimeoutTimerRef.current = null
    roundTimeoutDeadlineRef.current = null
    roundTimeoutRemainingMsRef.current = null
    if (!canContinueRoundTimers()) return

    unitLockedRef.current = true
    appendUnitResult(false, buildTimeoutRoundDetail())
    showAttemptFeedback(false)
    scheduleNextRound()
  }

  function startRoundTimeout(timeoutMs: number) {
    if (roundTimeoutTimerRef.current) {
      clearTimeout(roundTimeoutTimerRef.current)
      roundTimeoutTimerRef.current = null
    }
    if (!canContinueRoundTimers()) return

    const normalizedTimeoutMs = Math.max(0, timeoutMs)
    roundTimeoutDeadlineRef.current = Date.now() + normalizedTimeoutMs
    roundTimeoutRemainingMsRef.current = normalizedTimeoutMs
    roundTimeoutTimerRef.current = setTimeout(handleRoundTimeout, normalizedTimeoutMs)
  }

  function pauseRoundTimeout() {
    if (!roundTimeoutTimerRef.current) return
    clearTimeout(roundTimeoutTimerRef.current)
    roundTimeoutTimerRef.current = null
    const deadline = roundTimeoutDeadlineRef.current
    if (deadline !== null) {
      roundTimeoutRemainingMsRef.current = Math.max(0, deadline - Date.now())
    }
    roundTimeoutDeadlineRef.current = null
  }

  function resumeRoundTimeout(defaultTimeoutMs: number) {
    startRoundTimeout(roundTimeoutRemainingMsRef.current ?? defaultTimeoutMs)
  }

  function colorRevealDurationMs(round: ColorSequenceRound): number {
    return Math.max(1800, round.sequence.length * round.revealMs)
  }

  function patternRevealDurationMs(round: PatternSequenceRound): number {
    return Math.max(1800, round.sequence.length * round.revealMs)
  }

  function startColorRevealTimer(round: ColorSequenceRound, durationMs = colorRevealDurationMs(round)) {
    if (revealTimerRef.current) {
      clearTimeout(revealTimerRef.current)
    }
    const normalizedDurationMs = Math.max(0, durationMs)
    revealTimerDeadlineRef.current = Date.now() + normalizedDurationMs
    revealTimerRemainingMsRef.current = normalizedDurationMs
    revealTimerRef.current = setTimeout(() => {
      revealTimerRef.current = null
      revealTimerDeadlineRef.current = null
      revealTimerRemainingMsRef.current = null
      if (phaseRef.current === 'playing') {
        setColorRevealing(false)
        roundStartedAtRef.current = Date.now()
        startRoundTimeout(round.inputTimeoutMs)
      }
    }, normalizedDurationMs)
  }

  function startPatternRevealTimer(round: PatternSequenceRound, durationMs = patternRevealDurationMs(round)) {
    if (revealTimerRef.current) {
      clearTimeout(revealTimerRef.current)
    }
    const normalizedDurationMs = Math.max(0, durationMs)
    revealTimerDeadlineRef.current = Date.now() + normalizedDurationMs
    revealTimerRemainingMsRef.current = normalizedDurationMs
    revealTimerRef.current = setTimeout(() => {
      revealTimerRef.current = null
      revealTimerDeadlineRef.current = null
      revealTimerRemainingMsRef.current = null
      if (phaseRef.current === 'playing') {
        setPatternRevealing(false)
        roundStartedAtRef.current = Date.now()
        startRoundTimeout(round.inputTimeoutMs)
      }
    }, normalizedDurationMs)
  }

  function startPuzzlePreviewTimer(round: PuzzleRound, durationMs = round.previewMs) {
    if (revealTimerRef.current) {
      clearTimeout(revealTimerRef.current)
    }
    const normalizedDurationMs = Math.max(0, durationMs)
    revealTimerDeadlineRef.current = Date.now() + normalizedDurationMs
    revealTimerRemainingMsRef.current = normalizedDurationMs
    revealTimerRef.current = setTimeout(() => {
      revealTimerRef.current = null
      revealTimerDeadlineRef.current = null
      revealTimerRemainingMsRef.current = null
      if (phaseRef.current === 'playing') {
        setPuzzlePreviewing(false)
        roundStartedAtRef.current = Date.now()
      }
    }, normalizedDurationMs)
  }

  function pauseRevealTimer() {
    if (!revealTimerRef.current) return
    clearTimeout(revealTimerRef.current)
    revealTimerRef.current = null
    const deadline = revealTimerDeadlineRef.current
    if (deadline !== null) {
      revealTimerRemainingMsRef.current = Math.max(0, deadline - Date.now())
    }
    revealTimerDeadlineRef.current = null
  }

  function startColorRound() {
    if (endStartedRef.current || phaseRef.current !== 'playing') return
    clearRoundTimers()
    pendingNextRoundRef.current = false
    const round = createColorSequenceRound(difficultyRef.current)
    unitLockedRef.current = false
    activeColorInputRef.current = []
    activeColorRoundRef.current = round
    activePatternRoundRef.current = null
    activeCategoryRoundRef.current = null
    activeSoundRoundRef.current = null
    activePuzzleRoundRef.current = null
    soundRoundRunIdRef.current += 1
    soundPreviewInFlightRef.current = false
    setActiveColorRound(round)
    setActiveColorInput([])
    setActiveInhibitionRound(null)
    setActivePatternRound(null)
    setActivePatternInput([])
    setPatternRevealing(false)
    setActiveCategoryRound(null)
    setActiveSoundRound(null)
    setActivePuzzleRound(null)
    setSoundPlaybackError('')
    setPuzzlePreviewing(false)
    setFeedback('')
    setColorRevealing(true)
    startColorRevealTimer(round)
  }

  function startInhibitionRound() {
    if (endStartedRef.current || phaseRef.current !== 'playing') return
    clearRoundTimers()
    pendingNextRoundRef.current = false
    unitLockedRef.current = false
    activeColorInputRef.current = []
    const round = createInhibitionRound(difficultyRef.current)
    roundStartedAtRef.current = Date.now()
    activeColorRoundRef.current = null
    activePatternRoundRef.current = null
    activeCategoryRoundRef.current = null
    activeSoundRoundRef.current = null
    activePuzzleRoundRef.current = null
    soundRoundRunIdRef.current += 1
    soundPreviewInFlightRef.current = false
    setActiveInhibitionRound(round)
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setActivePatternRound(null)
    setActivePatternInput([])
    setPatternRevealing(false)
    setActiveCategoryRound(null)
    setActiveSoundRound(null)
    setActivePuzzleRound(null)
    setSoundPlaybackError('')
    setPuzzlePreviewing(false)
    setFeedback('')
    startRoundTimeout(round.timeoutMs)
  }

  function startPatternRound() {
    if (endStartedRef.current || phaseRef.current !== 'playing') return
    clearRoundTimers()
    pendingNextRoundRef.current = false
    const round = createPatternSequenceRound(difficultyRef.current)
    unitLockedRef.current = false
    activeColorInputRef.current = []
    activePatternInputRef.current = []
    activeColorRoundRef.current = null
    activePatternRoundRef.current = round
    activeCategoryRoundRef.current = null
    activeSoundRoundRef.current = null
    activePuzzleRoundRef.current = null
    soundRoundRunIdRef.current += 1
    soundPreviewInFlightRef.current = false
    setActivePatternRound(round)
    setActivePatternInput([])
    setPatternRevealing(true)
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setActiveInhibitionRound(null)
    setActiveCategoryRound(null)
    setActiveSoundRound(null)
    setActivePuzzleRound(null)
    setSoundPlaybackError('')
    setPuzzlePreviewing(false)
    setFeedback('')
    startPatternRevealTimer(round)
  }

  function startCategoryRound() {
    if (endStartedRef.current || phaseRef.current !== 'playing') return
    clearRoundTimers()
    pendingNextRoundRef.current = false
    unitLockedRef.current = false
    activeColorInputRef.current = []
    activePatternInputRef.current = []
    const round = createCategorySwitchRound(difficultyRef.current, {
      previousRule: previousCategoryRuleRef.current,
    })
    previousCategoryRuleRef.current = round.rule
    roundStartedAtRef.current = Date.now()
    activeColorRoundRef.current = null
    activePatternRoundRef.current = null
    activeCategoryRoundRef.current = round
    activeSoundRoundRef.current = null
    activePuzzleRoundRef.current = null
    soundRoundRunIdRef.current += 1
    soundPreviewInFlightRef.current = false
    setActiveCategoryRound(round)
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setActivePatternRound(null)
    setActivePatternInput([])
    setPatternRevealing(false)
    setActiveInhibitionRound(null)
    setActiveSoundRound(null)
    setActivePuzzleRound(null)
    setSoundPlaybackError('')
    setPuzzlePreviewing(false)
    setFeedback('')
    startRoundTimeout(round.timeoutMs)
  }

  function startSoundRound() {
    if (endStartedRef.current || phaseRef.current !== 'playing') return
    clearRoundTimers()
    pendingNextRoundRef.current = false
    unitLockedRef.current = false
    activeColorInputRef.current = []
    activePatternInputRef.current = []
    roundStartedAtRef.current = Date.now()
    const round = createSoundDiscriminationRound(difficultyRef.current, SOUND_DISCRIMINATION_AUDIO)
    activeColorRoundRef.current = null
    activePatternRoundRef.current = null
    activeCategoryRoundRef.current = null
    activeSoundRoundRef.current = round
    activePuzzleRoundRef.current = null
    soundRoundRunIdRef.current += 1
    const runId = soundRoundRunIdRef.current
    soundPreviewInFlightRef.current = true
    setActiveSoundRound(round)
    setSoundRoundPhase('preview')
    setSoundPreviewingCardId(null)
    setSoundPlaybackError('')
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setActivePatternRound(null)
    setActivePatternInput([])
    setPatternRevealing(false)
    setActiveInhibitionRound(null)
    setActiveCategoryRound(null)
    setActivePuzzleRound(null)
    setPuzzlePreviewing(false)
    setFeedback('')
    void autoPreviewSoundRound(runId)
  }

  function startPuzzleRound() {
    if (endStartedRef.current || phaseRef.current !== 'playing') return
    clearRoundTimers()
    pendingNextRoundRef.current = false
    unitLockedRef.current = false
    activeColorInputRef.current = []
    activePatternInputRef.current = []
    const round = createPuzzleRound(difficultyRef.current)
    roundStartedAtRef.current = Date.now()
    activeColorRoundRef.current = null
    activePatternRoundRef.current = null
    activeCategoryRoundRef.current = null
    activeSoundRoundRef.current = null
    activePuzzleRoundRef.current = round
    soundRoundRunIdRef.current += 1
    soundPreviewInFlightRef.current = false
    setActivePuzzleRound(round)
    setSelectedPuzzleTileId(null)
    setPuzzlePreviewing(true)
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setActivePatternRound(null)
    setActivePatternInput([])
    setPatternRevealing(false)
    setActiveInhibitionRound(null)
    setActiveCategoryRound(null)
    setActiveSoundRound(null)
    setSoundPlaybackError('')
    setFeedback('')
    startPuzzlePreviewTimer(round)
  }

  function startRoundForGame(gameCodeValue: GameCode | null) {
    if (gameCodeValue === 'game-memory-color-sequence') {
      startColorRound()
    } else if (gameCodeValue === 'game-memory-pattern-sequence') {
      startPatternRound()
    } else if (gameCodeValue === 'game-executive-inhibition') {
      startInhibitionRound()
    } else if (gameCodeValue === 'game-executive-category-switch') {
      startCategoryRound()
    } else if (gameCodeValue === 'game-audiovisual-sound-discrimination') {
      startSoundRound()
    } else if (gameCodeValue === 'game-audiovisual-puzzle') {
      startPuzzleRound()
    }
  }

  function beginPlaying() {
    if (!actionRef.current || !gameCodeRef.current || endStartedRef.current) return
    targetSecondsRef.current = suggestedDurationMinutes(actionRef.current) * 60
    elapsedSecondsRef.current = 0
    unitResultsRef.current = []
    unitLockedRef.current = false
    setElapsedSeconds(0)
    setUnitResults([])
    setFeedback('')
    setSessionPhase('playing')
    startRoundForGame(gameCodeRef.current)
  }

  async function playIntroTimedStep(key: GameAudioKey, minMs: number) {
    setIntroText(GAME_AUDIO_TEXT[key])
    await Promise.all([playGameAudio(key).catch(() => undefined), wait(minMs)])
  }

  function isIntroRunActive(runId: number): boolean {
    return introRunIdRef.current === runId && phaseRef.current === 'intro'
  }

  async function startIntro() {
    if (phaseRef.current !== 'setup') return
    if (!actionIsGame || !action) {
      setError('游戏动作无效，请返回当前运动计划重新进入')
      return
    }
    if (!gameCode) {
      setError('该游戏暂未上线，请返回当前运动计划选择已上线游戏')
      return
    }
    if (adjustedDifficulty && !difficultyReason.trim()) {
      setError('调整难度后需要填写原因')
      return
    }

    resetSessionState()
    const runId = introRunIdRef.current + 1
    introRunIdRef.current = runId
    setError('')
    setSessionPhase('intro')
    const introKey: GameAudioKey = GAME_CATALOG[gameCode].introAudioKey
    const steps = createGameIntroSteps(introKey)
    for (const { key, minMs } of steps) {
      if (!isIntroRunActive(runId)) return
      await playIntroTimedStep(key, minMs)
      if (!isIntroRunActive(runId)) return
    }
    if (!isIntroRunActive(runId)) return
    beginPlaying()
  }

  function responseMs(): number {
    return Math.max(0, Date.now() - roundStartedAtRef.current)
  }

  function withBaseRoundDetail(detail: Record<string, unknown>): Record<string, unknown> {
    return {
      game_code: gameCodeRef.current,
      difficulty: difficultyRef.current,
      response_ms: responseMs(),
      ...detail,
    }
  }

  function soundRoundSummaryDetail(
    round: SoundDiscriminationRound,
    detail: { result?: string; correct?: boolean }
  ): Record<string, unknown> {
    return withBaseRoundDetail({
      game_kind: 'sound_discrimination',
      card_count: round.cards.length,
      previewed_count: round.cards.filter((card) => card.previewed).length,
      ...detail,
    })
  }

  function buildTimeoutRoundDetail(): Record<string, unknown> {
    const colorRound = activeColorRoundRef.current
    const patternRound = activePatternRoundRef.current
    const categoryRound = activeCategoryRoundRef.current
    const soundRound = activeSoundRoundRef.current
    if (gameCodeRef.current === 'game-memory-color-sequence' && colorRound) {
      return withBaseRoundDetail({
        result: 'timeout',
        target: colorRound.sequence,
        selected: activeColorInputRef.current,
      })
    }
    if (gameCodeRef.current === 'game-memory-pattern-sequence' && patternRound) {
      return withBaseRoundDetail({
        result: 'timeout',
        target: patternRound.sequence.map((item) => item.id),
        selected: activePatternInputRef.current,
      })
    }
    if (gameCodeRef.current === 'game-executive-category-switch' && categoryRound) {
      return withBaseRoundDetail({
        result: 'timeout',
        rule: categoryRound.rule,
        target: categoryRound.correctOption,
        selected: null,
        item: categoryRound.item.id,
      })
    }
    if (gameCodeRef.current === 'game-audiovisual-sound-discrimination' && soundRound) {
      return soundRoundSummaryDetail(soundRound, {
        result: 'timeout',
      })
    }
    return withBaseRoundDetail({ result: 'timeout' })
  }

  function appendUnitResult(correct: boolean, detail?: Record<string, unknown>) {
    const nextResults = [...unitResultsRef.current, { correct, detail }]
    unitResultsRef.current = nextResults
    setUnitResults(nextResults)
  }

  function scheduleNextRound() {
    clearRoundTimers()
    pendingNextRoundRef.current = true
    nextRoundTimerRef.current = setTimeout(() => {
      nextRoundTimerRef.current = null
      if (phaseRef.current !== 'playing' || endStartedRef.current || elapsedSecondsRef.current >= targetSecondsRef.current) return
      startRoundForGame(gameCodeRef.current)
    }, 650)
  }

  function pauseGame() {
    if (phaseRef.current !== 'playing') return
    stopActiveGameAudio()
    setSoundPreviewingCardId(null)
    if (colorRevealing || patternRevealing || puzzlePreviewing) {
      pauseRevealTimer()
    }
    pauseRoundTimeout()
    clearRoundTimers({ preserveRevealRemaining: true, preserveRoundTimeoutRemaining: true })
    setSessionPhase('paused')
  }

  function resumeGame() {
    if (phaseRef.current !== 'paused') return
    setSessionPhase('playing')
    if (pendingNextRoundRef.current || unitLockedRef.current) {
      scheduleNextRound()
      return
    }
    if (gameCodeRef.current === 'game-memory-color-sequence' && colorRevealing && activeColorRound) {
      setColorRevealing(true)
      startColorRevealTimer(activeColorRound, revealTimerRemainingMsRef.current ?? colorRevealDurationMs(activeColorRound))
      return
    }
    if (gameCodeRef.current === 'game-memory-pattern-sequence' && patternRevealing && activePatternRound) {
      setPatternRevealing(true)
      startPatternRevealTimer(activePatternRound, revealTimerRemainingMsRef.current ?? patternRevealDurationMs(activePatternRound))
      return
    }
    if (gameCodeRef.current === 'game-audiovisual-puzzle' && puzzlePreviewing && activePuzzleRound) {
      setPuzzlePreviewing(true)
      startPuzzlePreviewTimer(activePuzzleRound, revealTimerRemainingMsRef.current ?? activePuzzleRound.previewMs)
      return
    }
    if (gameCodeRef.current === 'game-memory-color-sequence' && activeColorRound) {
      resumeRoundTimeout(activeColorRound.inputTimeoutMs)
      return
    }
    if (gameCodeRef.current === 'game-memory-pattern-sequence' && activePatternRound) {
      resumeRoundTimeout(activePatternRound.inputTimeoutMs)
      return
    }
    if (gameCodeRef.current === 'game-executive-inhibition' && activeInhibitionRound) {
      resumeRoundTimeout(activeInhibitionRound.timeoutMs)
      return
    }
    if (gameCodeRef.current === 'game-executive-category-switch' && activeCategoryRound) {
      resumeRoundTimeout(activeCategoryRound.timeoutMs)
      return
    }
    if (gameCodeRef.current === 'game-audiovisual-sound-discrimination' && activeSoundRound && soundPhase === 'preview') {
      soundPreviewInFlightRef.current = true
      void autoPreviewSoundRound(soundRoundRunIdRef.current)
      return
    }
    if (gameCodeRef.current === 'game-audiovisual-sound-discrimination' && activeSoundRound && soundPhase === 'choose') {
      resumeRoundTimeout(activeSoundRound.timeoutMs)
    }
  }

  function selectColor(color: ColorToken) {
    if (phaseRef.current !== 'playing' || colorRevealing || unitLockedRef.current || !activeColorRound) return
    void playGameAudio('tap')
    const nextInput = [...activeColorInputRef.current, color]
    activeColorInputRef.current = nextInput
    setActiveColorInput(nextInput)

    if (nextInput.length < activeColorRound.sequence.length) return

    unitLockedRef.current = true
    const attempt = evaluateColorSequenceAttempt(activeColorRound.sequence, nextInput)
    appendUnitResult(
      attempt.correct,
      withBaseRoundDetail({
        target: activeColorRound.sequence,
        selected: nextInput,
        correct: attempt.correct,
      })
    )
    showAttemptFeedback(attempt.correct)
    scheduleNextRound()
  }

  function selectInhibition(index: number) {
    if (phaseRef.current !== 'playing' || unitLockedRef.current || !activeInhibitionRound) return
    unitLockedRef.current = true
    void playGameAudio('tap')
    const attempt = evaluateInhibitionAttempt(activeInhibitionRound, index)
    appendUnitResult(
      attempt.correct,
      withBaseRoundDetail({
        target: activeInhibitionRound.correctIndex,
        selected: index,
        correct: attempt.correct,
        options: activeInhibitionRound.options,
      })
    )
    showAttemptFeedback(attempt.correct)
    scheduleNextRound()
  }

  function selectPattern(pattern: PatternToken) {
    if (phaseRef.current !== 'playing' || patternRevealing || unitLockedRef.current || !activePatternRound) return
    void playGameAudio('tap')
    const nextInput = [...activePatternInputRef.current, pattern.id]
    activePatternInputRef.current = nextInput
    setActivePatternInput(nextInput)

    if (nextInput.length < activePatternRound.sequence.length) return

    unitLockedRef.current = true
    const expected = activePatternRound.sequence.map((item) => item.id)
    const attempt = evaluatePatternSequenceAttempt(expected, nextInput)
    appendUnitResult(
      attempt.correct,
      withBaseRoundDetail({
        target: expected,
        selected: nextInput,
        correct: attempt.correct,
      })
    )
    showAttemptFeedback(attempt.correct)
    scheduleNextRound()
  }

  function selectCategory(option: string) {
    if (phaseRef.current !== 'playing' || unitLockedRef.current || !activeCategoryRound) return
    unitLockedRef.current = true
    void playGameAudio('tap')
    const attempt = evaluateCategorySwitchAttempt(activeCategoryRound, option)
    appendUnitResult(
      attempt.correct,
      withBaseRoundDetail({
        rule: activeCategoryRound.rule,
        item: activeCategoryRound.item.id,
        target: activeCategoryRound.correctOption,
        selected: option,
        correct: attempt.correct,
      })
    )
    showAttemptFeedback(attempt.correct)
    scheduleNextRound()
  }

  function canUseSoundPreviewRun(runId: number): boolean {
    return (
      soundRoundRunIdRef.current === runId &&
      phaseRef.current === 'playing' &&
      soundPhaseRef.current === 'preview' &&
      !unitLockedRef.current &&
      !endStartedRef.current
    )
  }

  async function autoPreviewSoundRound(runId: number) {
    setSoundPlaybackError('')
    try {
      while (canUseSoundPreviewRun(runId)) {
        const latestRound = activeSoundRoundRef.current
        if (!latestRound) return
        const card = nextSoundPreviewCard(latestRound)
        if (!card) break

        const nextRound = markCardPreviewed(latestRound, card.id)
        activeSoundRoundRef.current = nextRound
        setActiveSoundRound(nextRound)
        setSoundPreviewingCardId(card.id)

        const previewPlayed = await playAudioSrc(card.audioSrc)
        if (!canUseSoundPreviewRun(runId)) return
        if (!previewPlayed) {
          setSoundPlaybackError('声音播放异常，已继续播放下一张')
        }
      }

      const latestRound = activeSoundRoundRef.current
      if (!latestRound || !latestRound.previewComplete || !canUseSoundPreviewRun(runId)) return

      setSoundRoundPhase('choose')
      setSoundPreviewingCardId(null)
      soundPreviewInFlightRef.current = false
      roundStartedAtRef.current = Date.now()
      const targetPlayed = await playAudioSrc(latestRound.target.audioSrc)
      if (
        soundRoundRunIdRef.current !== runId ||
        activeSoundRoundRef.current !== latestRound ||
        currentSoundRoundPhase() !== 'choose' ||
        phaseRef.current !== 'playing' ||
        unitLockedRef.current ||
        endStartedRef.current
      ) {
        return
      }
      if (!targetPlayed) {
        setSoundPlaybackError('目标声音播放异常，请点击重播目标声音')
      }
      startRoundTimeout(latestRound.timeoutMs)
    } finally {
      if (soundRoundRunIdRef.current === runId) {
        soundPreviewInFlightRef.current = false
        setSoundPreviewingCardId(null)
      }
    }
  }

  async function replayTargetSound() {
    const runId = soundRoundRunIdRef.current
    const currentRound = activeSoundRoundRef.current
    if (phaseRef.current !== 'playing' || !currentRound || soundPhaseRef.current !== 'choose') return
    setSoundPlaybackError('')
    const played = await playAudioSrc(currentRound.target.audioSrc)
    if (
      soundRoundRunIdRef.current !== runId ||
      activeSoundRoundRef.current !== currentRound ||
      currentSoundRoundPhase() !== 'choose' ||
      phaseRef.current !== 'playing' ||
      unitLockedRef.current ||
      endStartedRef.current
    ) {
      return
    }
    if (!played) {
      setSoundPlaybackError('目标声音播放异常，请再次点击重播')
    }
  }

  function selectSoundCard(card: SoundCard) {
    if (phaseRef.current !== 'playing' || soundPhaseRef.current !== 'choose' || unitLockedRef.current || !activeSoundRound) return
    unitLockedRef.current = true
    void playGameAudio('tap')
    const attempt = evaluateSoundDiscriminationAttempt(activeSoundRound, card.soundId)
    appendUnitResult(
      attempt.correct,
      soundRoundSummaryDetail(activeSoundRound, {
        result: 'answered',
        correct: attempt.correct,
      })
    )
    showAttemptFeedback(attempt.correct)
    scheduleNextRound()
  }

  function selectPuzzleTile(tile: PuzzleTile) {
    if (phaseRef.current !== 'playing' || puzzlePreviewing || unitLockedRef.current || !activePuzzleRound) return
    void playGameAudio('tap')
    if (!selectedPuzzleTileId) {
      setSelectedPuzzleTileId(tile.id)
      return
    }

    const nextTiles = swapPuzzleTiles(activePuzzleRound.tiles, selectedPuzzleTileId, tile.id)
    const nextRound = { ...activePuzzleRound, tiles: nextTiles }
    activePuzzleRoundRef.current = nextRound
    setActivePuzzleRound(nextRound)
    setSelectedPuzzleTileId(null)

    if (evaluatePuzzleCompletion(nextTiles)) {
      unitLockedRef.current = true
      appendUnitResult(
        true,
        withBaseRoundDetail({
          image_key: activePuzzleRound.imageKey,
          grid: `${activePuzzleRound.rows}x${activePuzzleRound.cols}`,
          selected: [selectedPuzzleTileId, tile.id],
          correct: true,
        })
      )
      showAttemptFeedback(true)
      scheduleNextRound()
    }
  }

  async function uploadResult(payload: GameTrainingPayload) {
    setUploadState('uploading')
    try {
      await postGameTrainingRecord(payload)
      setUploadState('uploaded')
    } catch (err) {
      const uploadError = err as Partial<TrainingRecordUploadError>
      const message = err instanceof Error ? err.message : '上传失败'
      if (!uploadError.retryable) {
        setUploadState('upload_rejected')
        setError(message)
        return
      }

      try {
        const pending = await savePendingGameUploadAfterActiveRetry(Taro, payload)
        if (pending.payload === payload) {
          setUploadState('pending_retry')
          setError(`上传失败，已保存待补传记录：${message}`)
          startPendingGameUploadRetryLoop(Taro)
        } else {
          setUploadState('blocked_by_existing_pending')
          setError('已有待上传记录，本次结果未覆盖旧记录，请先返回后等待或处理旧记录')
        }
      } catch {
        setUploadState('upload_save_failed')
        setError('上传失败，且本地待补传保存失败，请联系指导老师确认记录')
      }
    }
  }

  function endSession(reason: GameEndReason, durationSeconds = elapsedSecondsRef.current) {
    if (endStartedRef.current) return
    const currentAction = actionRef.current
    const currentGameCode = gameCodeRef.current
    if (!currentAction || !currentGameCode) return

    endStartedRef.current = true
    introRunIdRef.current += 1
    clearRoundTimers()
    stopActiveGameAudio()
    const finalDurationSeconds =
      reason === 'timer'
        ? targetSecondsRef.current
        : Math.max(0, Math.min(durationSeconds, targetSecondsRef.current))
    const results = unitResultsRef.current
    const base = buildGameTrainingResult({
      gameCode: currentGameCode,
      prescribedDifficulty: normalizeDifficulty(currentAction.difficulty),
      actualDifficulty: difficultyRef.current,
      difficultyAdjustReason: difficultyReasonRef.current.trim(),
      endedBy: reason,
      durationSeconds: finalDurationSeconds,
      suggestedDurationMinutes: suggestedDurationMinutes(currentAction),
      completedUnits: results.length,
      correctUnits: results.filter((item) => item.correct).length,
      uploadMode: 'direct',
      retryCount: 0,
      totalRetryCount: 0,
    })
    const payload: GameTrainingPayload = {
      ...base,
      form_data: {
        ...base.form_data,
        raw_detail: {
          ...base.form_data.raw_detail,
          rounds: results.map((item, index) => ({
            round_index: index + 1,
            correct: item.correct,
            ...(item.detail ?? {}),
          })),
        },
      },
      prescription_action: currentAction.id,
      training_date: todayLocalDate(),
      note: reason === 'manual' ? '用户提前结束本次游戏训练' : '',
    }
    elapsedSecondsRef.current = finalDurationSeconds
    setElapsedSeconds(finalDurationSeconds)
    setResultPayload(payload)
    setFeedback('')
    setSessionPhase('result')
    void playGameAudio(reason === 'manual' ? 'manual_end' : 'complete')
    if (demoMode) {
      setUploadState('demo_local')
    } else {
      void uploadResult(payload)
    }
  }

  function renderGameTopBar() {
    return (
      <View className='game-topbar'>
        <View className='game-timer-strip'>
          <Text className='game-timer-label'>剩余时间</Text>
          <Text className='game-timer-value'>{formatClock(remainingSeconds)}</Text>
        </View>
        <View className='game-control-bar'>
          <Button className='secondary-button compact-button' onClick={phase === 'paused' ? resumeGame : pauseGame}>
            {phase === 'paused' ? '继续' : '暂停'}
          </Button>
          <Button
            className='secondary-button compact-button'
            onClick={() => {
              const nextMuted = !muted
              setMuted(nextMuted)
              setGameAudioMuted(nextMuted)
            }}
          >
            {muted ? '开启声音' : '关闭声音'}
          </Button>
          <Button className='secondary-button compact-button danger-button' onClick={() => endSession('manual')}>
            提前结束
          </Button>
        </View>
      </View>
    )
  }

  function renderColorSequenceGame() {
    if (!activeColorRound) {
      return (
        <View className='page game-session-page hainan-game-page game-play-page'>
          {renderGameTopBar()}
          <Text className='muted'>正在生成本轮题目</Text>
        </View>
      )
    }

    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title'>
          {phase === 'paused' ? '训练已暂停' : colorRevealing ? '请记住这个颜色顺序' : '请按刚才的顺序点击颜色'}
        </Text>
        {phase !== 'paused' ? (
          <View className='sequence-preview'>
            {colorRevealing
              ? activeColorRound.sequence.map((color, index) => (
                  <Text key={`${color}-${index}`} className={`sequence-chip color-${color}`}>
                    {COLOR_LABEL[color]}
                  </Text>
                ))
              : activeColorRound.sequence.map((_color, index) => (
                  <Text key={index} className='sequence-chip hidden-chip'>
                    {index < activeColorInput.length ? '已选' : index + 1}
                  </Text>
                ))}
          </View>
        ) : null}
        <View className='game-stage color-grid'>
          {activeColorRound.colors.map((color) => (
            <Button
              key={color}
              className={`color-tile color-${color}`}
              disabled={phase !== 'playing' || colorRevealing || unitLockedRef.current}
              onClick={() => selectColor(color)}
            >
              {COLOR_LABEL[color]}
            </Button>
          ))}
        </View>
        {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
      </View>
    )
  }

  function renderInhibitionGame() {
    if (!activeInhibitionRound) {
      return (
        <View className='page game-session-page hainan-game-page game-play-page'>
          {renderGameTopBar()}
          <Text className='muted'>正在生成本轮题目</Text>
        </View>
      )
    }

    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title game-task-title inhibition-task-title'>请选择不一样的数字</Text>
        <View className='game-stage number-grid'>
          {activeInhibitionRound.options.map((value, index) => (
            <Button
              key={`${value}-${index}`}
              className='number-tile'
              disabled={phase !== 'playing' || unitLockedRef.current}
              onClick={() => selectInhibition(index)}
            >
              {value}
            </Button>
          ))}
        </View>
        {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
      </View>
    )
  }

  function renderLoadingRound() {
    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        <Text className='muted'>正在生成本轮题目</Text>
      </View>
    )
  }

  function renderPatternSequenceGame() {
    if (!activePatternRound) return renderLoadingRound()

    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title'>
          {phase === 'paused' ? '训练已暂停' : patternRevealing ? '请记住这个图案顺序' : '请按刚才的顺序点击图案'}
        </Text>
        {phase !== 'paused' ? (
          <View className='sequence-preview'>
            {patternRevealing
              ? activePatternRound.sequence.map((pattern, index) => (
                  <View key={`${pattern.id}-${index}`} className='image-sequence-chip'>
                    <Image className='game-image' src={pattern.imageSrc} mode='aspectFit' />
                    <Text>{pattern.label}</Text>
                  </View>
                ))
              : activePatternRound.sequence.map((_pattern, index) => (
                  <Text key={index} className='sequence-chip hidden-chip'>
                    {index < activePatternInput.length ? '已选' : index + 1}
                  </Text>
                ))}
          </View>
        ) : null}
        <View className='game-stage pattern-grid'>
          {activePatternRound.patterns.map((pattern) => (
            <Button
              key={pattern.id}
              className='image-tile'
              hoverClass='game-card-pressed'
              disabled={phase !== 'playing' || patternRevealing || unitLockedRef.current}
              onClick={() => selectPattern(pattern)}
            >
              <View className='game-card-face'>
                <Image className='game-image game-card-image' src={pattern.imageSrc} mode='aspectFit' />
                <Text className='game-card-label'>{pattern.label}</Text>
              </View>
            </Button>
          ))}
        </View>
        {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
      </View>
    )
  }

  function renderCategorySwitchGame() {
    if (!activeCategoryRound) return renderLoadingRound()

    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title'>{phase === 'paused' ? '训练已暂停' : activeCategoryRound.ruleLabel}</Text>
        <View className='game-stage category-card'>
          <Image className='category-image' src={activeCategoryRound.item.imageSrc} mode='aspectFit' />
          <Text className='category-label'>{activeCategoryRound.item.label}</Text>
        </View>
        <View className='category-options'>
          {activeCategoryRound.options.map((option) => (
            <Button
              key={option}
              className='category-option'
              hoverClass='game-card-pressed'
              disabled={phase !== 'playing' || unitLockedRef.current}
              onClick={() => selectCategory(option)}
            >
              {option}
            </Button>
          ))}
        </View>
        {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
      </View>
    )
  }

  function renderSoundDiscriminationGame() {
    if (!activeSoundRound) return renderLoadingRound()

    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title'>
          {phase === 'paused'
            ? '训练已暂停'
            : soundPhase === 'preview'
              ? '正在依次试听卡片'
              : '请听目标声音，选择对应卡片'}
        </Text>
        {soundPhase === 'choose' ? (
          <Button className='secondary-button replay-button' disabled={phase !== 'playing'} onClick={replayTargetSound}>
            重播目标声音
          </Button>
        ) : null}
        {soundPlaybackError ? <Text className='error'>{soundPlaybackError}</Text> : null}
        <View className='game-stage sound-card-grid'>
          {activeSoundRound.cards.map((card) => {
            const revealed = card.previewed
            const previewing = soundPreviewingCardId === card.id
            return (
              <Button
                key={card.id}
                className={`sound-card ${revealed ? 'revealed' : ''} ${previewing ? 'previewing' : ''}`}
                hoverClass='game-card-pressed'
                disabled={phase !== 'playing' || unitLockedRef.current || soundPhase === 'preview'}
                onClick={() => {
                  if (soundPhase === 'choose') {
                    selectSoundCard(card)
                  }
                }}
              >
                {revealed ? (
                  <View className='sound-card-face'>
                    <Image className='game-image game-card-image' src={card.imageSrc} mode='aspectFit' />
                    <Text className='game-card-label'>{SOUND_CATEGORY_LABEL[card.category]}</Text>
                  </View>
                ) : (
                  <Text className='card-back'>?</Text>
                )}
              </Button>
            )
          })}
        </View>
        {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
      </View>
    )
  }

  function renderPuzzleGame() {
    if (!activePuzzleRound) return renderLoadingRound()

    return (
      <View className='page game-session-page hainan-game-page game-play-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title'>
          {phase === 'paused' ? '训练已暂停' : puzzlePreviewing ? '请记住完整图片' : '点击两块拼图交换位置'}
        </Text>
        {puzzlePreviewing || phase === 'paused' ? (
          <View className='game-stage puzzle-preview-board'>
            <Image className='puzzle-preview-image' src={activePuzzleRound.imageSrc} mode='aspectFill' />
          </View>
        ) : (
          <View className={`game-stage puzzle-grid puzzle-grid-${activePuzzleRound.cols}`}>
            {activePuzzleRound.tiles.map((tile) => (
              <Button
                key={tile.id}
                className={`puzzle-tile ${selectedPuzzleTileId === tile.id ? 'selected' : ''}`}
                hoverClass='game-card-pressed'
                onClick={() => selectPuzzleTile(tile)}
              >
                <View className='puzzle-tile-slice'>
                  <Image
                    className='puzzle-tile-image'
                    src={activePuzzleRound.imageSrc}
                    mode='scaleToFill'
                    style={puzzleTileImageStyle(activePuzzleRound, tile)}
                  />
                </View>
              </Button>
            ))}
          </View>
        )}
        {feedback ? <Text className='game-feedback'>{feedback}</Text> : null}
      </View>
    )
  }

  if (!loaded || phase === 'loading') {
    return (
      <View className='page game-session-page hainan-game-page game-state-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='muted'>加载当前运动计划中</Text>
      </View>
    )
  }

  if (!prescription && error) {
    return (
      <View className='page game-session-page hainan-game-page game-state-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>{error}</Text>
      </View>
    )
  }

  if (!prescription) {
    return (
      <View className='page game-session-page hainan-game-page game-state-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='muted'>暂无生效运动计划，暂时无法开始游戏训练</Text>
      </View>
    )
  }

  if (!action || !actionIsGame) {
    return (
      <View className='page game-session-page hainan-game-page game-state-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>游戏动作无效，请返回当前运动计划重新进入</Text>
      </View>
    )
  }

  if (!gameCode) {
    return (
      <View className='page game-session-page hainan-game-page game-state-page'>
        <Text className='title'>{action.action_name}</Text>
        <Text className='error'>该游戏暂未上线，请返回当前运动计划选择已上线游戏</Text>
      </View>
    )
  }

  if (phase === 'setup') {
    return (
      <View className='page game-session-page hainan-game-page game-setup-page'>
        <View className='game-hero'>
          <Text className='title'>{action.action_name}</Text>
          <Text className='paragraph'>{action.action_instruction || '按提示完成本次认知游戏训练。'}</Text>
          <Text className='muted'>{GAME_AUDIO_TEXT[GAME_CATALOG[gameCode].introAudioKey]}</Text>
        </View>

        <View className='panel game-summary-panel'>
          <View className='row'>
            <Text className='label'>本周进度</Text>
            <Text className='value'>
              {formatNumber(action.weekly_completed_count, '0')}/{formatNumber(action.weekly_target_count, '0')} 次
            </Text>
          </View>
          <View className='row'>
            <Text className='label'>运动计划建议时长</Text>
            <Text className='value'>{formatNumber(suggestedDurationMinutes(action), '10')} 分钟</Text>
          </View>
          <View className='row'>
            <Text className='label'>运动计划默认难度</Text>
            <Text className='value'>{prescribedDifficulty}</Text>
          </View>
        </View>

        <View className='field-card'>
          <Text className='label'>本次训练难度</Text>
          <Picker
            mode='selector'
            range={DIFFICULTY_OPTIONS}
            value={difficultyIndex}
            onChange={(event) => setDifficultyIndex(Number(event.detail.value))}
          >
            <Text className='value'>{difficulty}</Text>
          </Picker>
        </View>

        {adjustedDifficulty ? (
          <View className='field-card'>
            <Text className='label'>调整难度原因</Text>
            <Text className='muted'>请填写原因，指导老师端可见</Text>
            <Input
              className='input'
              value={difficultyReason}
              placeholder='例如：今天状态较好，想提高难度'
              onInput={(event) => setDifficultyReason(event.detail.value)}
            />
          </View>
        ) : null}

        {error ? <Text className='error'>{error}</Text> : null}

        <Button className='primary-button full-button' disabled={phase !== 'setup'} onClick={startIntro}>
          开始游戏
        </Button>
      </View>
    )
  }

  if (phase === 'intro') {
    return (
      <View className='page game-session-page hainan-game-page game-intro-page'>
        <View className='game-hero intro-hero'>
          <Text className='title'>{action.action_name}</Text>
          <Text className='countdown-text'>{introText || '准备开始'}</Text>
        </View>
        <Text className='muted'>声音播放失败也不会影响训练，请按文字提示继续。</Text>
      </View>
    )
  }

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-memory-color-sequence') {
    return renderColorSequenceGame()
  }

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-memory-pattern-sequence') {
    return renderPatternSequenceGame()
  }

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-executive-inhibition') {
    return renderInhibitionGame()
  }

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-executive-category-switch') {
    return renderCategorySwitchGame()
  }

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-audiovisual-sound-discrimination') {
    return renderSoundDiscriminationGame()
  }

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-audiovisual-puzzle') {
    return renderPuzzleGame()
  }

  if (phase === 'result') {
    const rawDetail = resultPayload?.form_data.raw_detail
    return (
      <View className='page game-session-page hainan-game-page game-result-page'>
        <View className='game-hero'>
          <Text className='eyebrow'>训练结果</Text>
          <Text className='title'>{resultPayload?.status === 'completed' ? '本次训练已完成' : '本次训练已提前结束'}</Text>
          <Text className='paragraph'>{textForEndReason(rawDetail?.ended_by ?? 'manual')}</Text>
        </View>

        {uploadState === 'pending_retry' ? (
          <Text className='pending-upload-banner'>{error || '上传失败，结果已进入待补传处理'}</Text>
        ) : null}
        {uploadState !== 'pending_retry' && error ? <Text className='error'>{error}</Text> : null}

        <View className='panel result-panel result-metrics'>
          <View className='row'>
            <Text className='label'>得分</Text>
            <Text className='value'>{formatNumber(resultPayload?.score)}</Text>
          </View>
          <View className='row'>
            <Text className='label'>正确率</Text>
            <Text className='value'>{formatNumber(resultPayload?.form_data.accuracy_rate)}%</Text>
          </View>
          <View className='row'>
            <Text className='label'>错误次数</Text>
            <Text className='value'>{formatNumber(resultPayload?.form_data.error_count)}</Text>
          </View>
          <View className='row'>
            <Text className='label'>实际难度</Text>
            <Text className='value'>{resultPayload?.form_data.difficulty ?? '-'}</Text>
          </View>
          <View className='row'>
            <Text className='label'>训练时长</Text>
            <Text className='value'>{formatNumber(resultPayload?.actual_duration_minutes)} 分钟</Text>
          </View>
          <View className='row'>
            <Text className='label'>结束方式</Text>
            <Text className='value'>{textForEndReason(rawDetail?.ended_by ?? 'manual')}</Text>
          </View>
          <View className='row'>
            <Text className='label'>完成题数</Text>
            <Text className='value'>
              {formatNumber(rawDetail?.correct_units)}/{formatNumber(rawDetail?.completed_units)}
            </Text>
          </View>
          <View className='row'>
            <Text className='label'>上传状态</Text>
            <Text className='value'>{uploadStateText(uploadState)}</Text>
          </View>
        </View>

        <Button
          className='primary-button full-button'
          onClick={() => demoMode
            ? Taro.redirectTo({ url: '/pages/prescription/index' })
            : Taro.navigateBack()}
        >
          返回运动计划
        </Button>
      </View>
    )
  }

  return (
    <View className='page game-session-page hainan-game-page game-state-page'>
      <Text className='title'>游戏训练</Text>
      <Text className='error'>当前训练状态异常，请返回当前运动计划重新进入</Text>
    </View>
  )
}
