import { Button, Input, Picker, Text, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useEffect, useMemo, useRef, useState } from 'react'

import { request } from '../../api/client'
import { clearPatientAppToken, getPatientAppToken } from '../../auth/token'
import type { CurrentPrescription } from '../../types/patientApp'
import { todayLocalDate } from '../../utils/date'
import {
  createColorSequenceRound,
  evaluateColorSequenceAttempt,
  type ColorSequenceRound,
  type ColorToken,
} from './colorSequence'
import { GAME_AUDIO_TEXT, isGameAudioMuted, playGameAudio, setGameAudioMuted, type GameAudioKey } from './gameAudio'
import type { GameActionSummary, GameCode, GameDifficulty, GameEndReason, GameTrainingPayload } from './gameTypes'
import { createInhibitionRound, evaluateInhibitionAttempt, type InhibitionRound } from './inhibition'
import { savePendingGameUpload } from './retryUpload'
import { buildGameTrainingResult } from './scoring'

type PrescriptionAction = NonNullable<CurrentPrescription>['actions'][number]

type SessionPhase = 'loading' | 'setup' | 'intro' | 'playing' | 'paused' | 'result'

type UnitResult = {
  correct: boolean
}

type UploadState =
  | 'idle'
  | 'uploading'
  | 'uploaded'
  | 'upload_rejected'
  | 'pending_retry'
  | 'blocked_by_existing_pending'
  | 'upload_save_failed'

const DIFFICULTY_OPTIONS: GameDifficulty[] = ['简单', '中等', '困难']
const API_BASE_URL = process.env.TARO_APP_API_BASE_URL || 'http://127.0.0.1:8000/api'
const RETRYABLE_STATUS_CODE_MIN = 500

const GAME_CODE_BY_SOURCE: Record<string, GameCode> = {
  'game-memory-color-sequence': 'game-memory-color-sequence',
  'game-executive-inhibition': 'game-executive-inhibition',
}

const COLOR_LABEL: Record<ColorToken, string> = {
  blue: '蓝',
  green: '绿',
  yellow: '黄',
  red: '红',
  teal: '青',
}

function normalizeDifficulty(value: string): GameDifficulty {
  return DIFFICULTY_OPTIONS.includes(value as GameDifficulty) ? (value as GameDifficulty) : '简单'
}

function gameCodeForAction(actionName: string): GameCode | null {
  if (actionName in GAME_CODE_BY_SOURCE) return GAME_CODE_BY_SOURCE[actionName]
  if (actionName.includes('颜色顺序记忆')) return 'game-memory-color-sequence'
  if (actionName.includes('反应抑制')) return 'game-executive-inhibition'
  return null
}

function suggestedDurationMinutes(action: GameActionSummary): number {
  return action.duration_minutes && action.duration_minutes > 0 ? action.duration_minutes : 10
}

function textForEndReason(reason: GameEndReason): string {
  return reason === 'timer' ? '已按处方建议时长完成' : '已提前结束，本次记录为部分完成'
}

function formatNumber(value: number | null | undefined, fallback = '-'): string {
  return value === null || value === undefined || !Number.isFinite(value) ? fallback : String(value)
}

function uploadStateText(uploadState: UploadState): string {
  if (uploadState === 'uploading') return '正在上传'
  if (uploadState === 'uploaded') return '已上传'
  if (uploadState === 'upload_rejected') return '上传失败'
  if (uploadState === 'pending_retry') return '待补传'
  if (uploadState === 'blocked_by_existing_pending') return '未保存，已有旧记录待补传'
  if (uploadState === 'upload_save_failed') return '未保存'
  return '等待上传'
}

function resolveErrorMessage(data: unknown): string {
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: unknown }).detail
    const message = (data as { message?: unknown }).message
    if (typeof detail === 'string') return detail
    if (typeof message === 'string') return message
  }
  return '请求失败'
}

type TrainingRecordUploadError = Error & {
  retryable: boolean
  statusCode?: number
}

function createUploadError(message: string, retryable: boolean, statusCode?: number): TrainingRecordUploadError {
  const error = new Error(message) as TrainingRecordUploadError
  error.retryable = retryable
  if (statusCode !== undefined) {
    error.statusCode = statusCode
  }
  return error
}

async function postGameTrainingRecord(payload: GameTrainingPayload): Promise<void> {
  const token = getPatientAppToken()
  let response: Taro.request.SuccessCallbackResult<Record<string, unknown>>
  try {
    response = await Taro.request<Record<string, unknown>>({
      url: `${API_BASE_URL}/patient-app/training-records/`,
      method: 'POST',
      data: payload,
      header: {
        'content-type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
  } catch (err) {
    throw createUploadError(err instanceof Error ? err.message : '网络异常，稍后自动补传', true)
  }

  const statusCode = Number(response.statusCode)
  if (!Number.isFinite(statusCode)) {
    throw createUploadError('网络异常，稍后自动补传', true)
  }
  if (statusCode >= 200 && statusCode < 300) return
  if (statusCode === 401 || statusCode === 403) {
    clearPatientAppToken()
    Taro.redirectTo({ url: '/pages/bind/index' })
    throw createUploadError('登录已失效', false, statusCode)
  }

  throw createUploadError(resolveErrorMessage(response.data), statusCode <= 0 || statusCode >= RETRYABLE_STATUS_CODE_MIN, statusCode)
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export default function GameSessionPage() {
  const router = useRouter()
  const actionId = Number(router.params.actionId)
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
  const activeColorInputRef = useRef<ColorToken[]>([])
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
  const initializedRef = useRef(false)
  const loadingPrescriptionRef = useRef(false)
  const loadedRef = useRef(false)
  const introRunIdRef = useRef(0)

  const action = useMemo<PrescriptionAction | null>(() => {
    return prescription?.actions.find((item) => item.id === actionId) ?? null
  }, [actionId, prescription])
  const actionIsGame = action?.internal_type === 'game'
  const gameCode = action ? gameCodeForAction(action.action_name) : null
  const difficulty = DIFFICULTY_OPTIONS[difficultyIndex] ?? '简单'
  const prescribedDifficulty = normalizeDifficulty(action?.difficulty ?? '')
  const adjustedDifficulty = difficulty !== prescribedDifficulty
  const remainingSeconds = Math.max(0, targetSecondsRef.current - elapsedSeconds)

  function setSessionPhase(nextPhase: SessionPhase) {
    phaseRef.current = nextPhase
    setPhase(nextPhase)
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

    request<CurrentPrescription>('/patient-app/current-prescription/')
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
    if (gameCode === 'game-executive-inhibition' && !activeInhibitionRound) {
      startInhibitionRound()
    }
  }, [activeColorRound, activeInhibitionRound, gameCode, phase])

  useEffect(() => {
    return () => {
      introRunIdRef.current += 1
      clearRoundTimers()
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
    appendUnitResult(false)
    setFeedback(GAME_AUDIO_TEXT.wrong)
    void playGameAudio('wrong')
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
        startRoundTimeout(round.inputTimeoutMs)
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
    setActiveColorRound(round)
    setActiveColorInput([])
    setActiveInhibitionRound(null)
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
    setActiveInhibitionRound(round)
    setActiveColorRound(null)
    setActiveColorInput([])
    setColorRevealing(false)
    setFeedback('')
    startRoundTimeout(round.timeoutMs)
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
    if (gameCodeRef.current === 'game-memory-color-sequence') {
      startColorRound()
    } else if (gameCodeRef.current === 'game-executive-inhibition') {
      startInhibitionRound()
    }
  }

  async function playIntroTimedStep(key: GameAudioKey, minMs: number) {
    setIntroText(GAME_AUDIO_TEXT[key])
    await Promise.all([playGameAudio(key).catch(() => undefined), wait(minMs)])
  }

  function isIntroRunActive(runId: number): boolean {
    return introRunIdRef.current === runId && phaseRef.current === 'intro'
  }

  async function startIntro() {
    if (!actionIsGame || !action) {
      setError('游戏动作无效，请返回当前处方重新进入')
      return
    }
    if (!gameCode) {
      setError('该游戏暂未上线，请返回当前处方选择已上线游戏')
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
    const introKey: GameAudioKey = gameCode === 'game-memory-color-sequence' ? 'color_intro' : 'inhibition_intro'
    const steps: Array<{ key: GameAudioKey; minMs: number }> = [
      { key: introKey, minMs: 1200 },
      { key: 'count_3', minMs: 700 },
      { key: 'count_2', minMs: 700 },
      { key: 'count_1', minMs: 700 },
      { key: 'start', minMs: 700 },
    ]
    for (const { key, minMs } of steps) {
      if (!isIntroRunActive(runId)) return
      await playIntroTimedStep(key, minMs)
      if (!isIntroRunActive(runId)) return
    }
    if (!isIntroRunActive(runId)) return
    beginPlaying()
  }

  function appendUnitResult(correct: boolean) {
    const nextResults = [...unitResultsRef.current, { correct }]
    unitResultsRef.current = nextResults
    setUnitResults(nextResults)
  }

  function scheduleNextRound() {
    clearRoundTimers()
    pendingNextRoundRef.current = true
    nextRoundTimerRef.current = setTimeout(() => {
      nextRoundTimerRef.current = null
      if (phaseRef.current !== 'playing' || endStartedRef.current || elapsedSecondsRef.current >= targetSecondsRef.current) return
      if (gameCodeRef.current === 'game-memory-color-sequence') {
        startColorRound()
      } else if (gameCodeRef.current === 'game-executive-inhibition') {
        startInhibitionRound()
      }
    }, 650)
  }

  function pauseGame() {
    if (phaseRef.current !== 'playing') return
    if (colorRevealing) {
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
    if (gameCodeRef.current === 'game-memory-color-sequence' && activeColorRound) {
      resumeRoundTimeout(activeColorRound.inputTimeoutMs)
      return
    }
    if (gameCodeRef.current === 'game-executive-inhibition' && activeInhibitionRound) {
      resumeRoundTimeout(activeInhibitionRound.timeoutMs)
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
    appendUnitResult(attempt.correct)
    setFeedback(attempt.correct ? GAME_AUDIO_TEXT.correct : GAME_AUDIO_TEXT.wrong)
    void playGameAudio(attempt.correct ? 'correct' : 'wrong')
    scheduleNextRound()
  }

  function selectInhibition(index: number) {
    if (phaseRef.current !== 'playing' || unitLockedRef.current || !activeInhibitionRound) return
    unitLockedRef.current = true
    void playGameAudio('tap')
    const attempt = evaluateInhibitionAttempt(activeInhibitionRound, index)
    appendUnitResult(attempt.correct)
    setFeedback(attempt.correct ? GAME_AUDIO_TEXT.correct : GAME_AUDIO_TEXT.wrong)
    void playGameAudio(attempt.correct ? 'correct' : 'wrong')
    scheduleNextRound()
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
        const pending = savePendingGameUpload(Taro, payload, Date.now())
        if (pending.payload === payload) {
          setUploadState('pending_retry')
          setError(`上传失败，已保存待补传记录：${message}`)
        } else {
          setUploadState('blocked_by_existing_pending')
          setError('已有待上传记录，本次结果未覆盖旧记录，请先返回后等待或处理旧记录')
        }
      } catch {
        setUploadState('upload_save_failed')
        setError('上传失败，且本地待补传保存失败，请联系医护确认记录')
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
      prescription_action: currentAction.id,
      training_date: todayLocalDate(),
      note: reason === 'manual' ? '患者提前结束本次游戏训练' : '',
    }
    elapsedSecondsRef.current = finalDurationSeconds
    setElapsedSeconds(finalDurationSeconds)
    setResultPayload(payload)
    setFeedback('')
    setSessionPhase('result')
    void playGameAudio(reason === 'manual' ? 'manual_end' : 'complete')
    void uploadResult(payload)
  }

  function renderGameTopBar() {
    return (
      <View className='game-topbar'>
        <Text className='game-stat'>剩余 {formatNumber(remainingSeconds, '0')} 秒</Text>
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
    )
  }

  function renderColorSequenceGame() {
    if (!activeColorRound) {
      return (
        <View className='page game-session-page hainan-game-page'>
          {renderGameTopBar()}
          <Text className='muted'>正在生成本轮题目</Text>
        </View>
      )
    }

    return (
      <View className='page game-session-page hainan-game-page'>
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
        <View className='color-grid'>
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
        <View className='page game-session-page hainan-game-page'>
          {renderGameTopBar()}
          <Text className='muted'>正在生成本轮题目</Text>
        </View>
      )
    }

    return (
      <View className='page game-session-page hainan-game-page'>
        {renderGameTopBar()}
        {phase === 'paused' ? <Text className='pending-upload-banner'>已暂停，点击继续后恢复训练</Text> : null}
        <Text className='section-title'>请选择不一样的数字</Text>
        <View className='number-grid'>
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

  if (!loaded || phase === 'loading') {
    return (
      <View className='page game-session-page hainan-game-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='muted'>加载当前处方中</Text>
      </View>
    )
  }

  if (!prescription && error) {
    return (
      <View className='page game-session-page hainan-game-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>{error}</Text>
      </View>
    )
  }

  if (!prescription) {
    return (
      <View className='page game-session-page hainan-game-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='muted'>暂无生效处方，暂时无法开始游戏训练</Text>
      </View>
    )
  }

  if (!action || !actionIsGame) {
    return (
      <View className='page game-session-page hainan-game-page'>
        <Text className='title'>游戏训练</Text>
        <Text className='error'>游戏动作无效，请返回当前处方重新进入</Text>
      </View>
    )
  }

  if (!gameCode) {
    return (
      <View className='page game-session-page hainan-game-page'>
        <Text className='title'>{action.action_name}</Text>
        <Text className='error'>该游戏暂未上线，请返回当前处方选择已上线游戏</Text>
      </View>
    )
  }

  if (phase === 'setup') {
    return (
      <View className='page game-session-page hainan-game-page'>
        <View className='game-hero'>
          <Text className='eyebrow'>海南康复训练</Text>
          <Text className='title'>{action.action_name}</Text>
          <Text className='paragraph'>{action.action_instruction || '按提示完成本次认知游戏训练。'}</Text>
          <Text className='muted'>
            {gameCode === 'game-memory-color-sequence' ? GAME_AUDIO_TEXT.color_intro : GAME_AUDIO_TEXT.inhibition_intro}
          </Text>
        </View>

        <View className='panel'>
          <View className='row'>
            <Text className='label'>本周进度</Text>
            <Text className='value'>
              {formatNumber(action.weekly_completed_count, '0')}/{formatNumber(action.weekly_target_count, '0')} 次
            </Text>
          </View>
          <View className='row'>
            <Text className='label'>处方建议时长</Text>
            <Text className='value'>{formatNumber(suggestedDurationMinutes(action), '10')} 分钟</Text>
          </View>
          <View className='row'>
            <Text className='label'>处方默认难度</Text>
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
            <Text className='muted'>请填写原因，医生端可见</Text>
            <Input
              className='input'
              value={difficultyReason}
              placeholder='例如：今天状态较好，想提高难度'
              onInput={(event) => setDifficultyReason(event.detail.value)}
            />
          </View>
        ) : null}

        {error ? <Text className='error'>{error}</Text> : null}

        <Button className='primary-button' onClick={startIntro}>
          开始游戏
        </Button>
      </View>
    )
  }

  if (phase === 'intro') {
    return (
      <View className='page game-session-page hainan-game-page'>
        <View className='game-hero intro-hero'>
          <Text className='eyebrow'>海南康复训练</Text>
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

  if ((phase === 'playing' || phase === 'paused') && gameCode === 'game-executive-inhibition') {
    return renderInhibitionGame()
  }

  if (phase === 'result') {
    const rawDetail = resultPayload?.form_data.raw_detail
    return (
      <View className='page game-session-page hainan-game-page'>
        <View className='game-hero'>
          <Text className='eyebrow'>训练结果</Text>
          <Text className='title'>{resultPayload?.status === 'completed' ? '本次训练已完成' : '本次训练已提前结束'}</Text>
          <Text className='paragraph'>{textForEndReason(rawDetail?.ended_by ?? 'manual')}</Text>
        </View>

        {uploadState === 'pending_retry' ? (
          <Text className='pending-upload-banner'>{error || '上传失败，结果已进入待补传处理'}</Text>
        ) : null}
        {uploadState !== 'pending_retry' && error ? <Text className='error'>{error}</Text> : null}

        <View className='panel result-panel'>
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

        <Button className='primary-button' onClick={() => Taro.navigateBack()}>
          返回处方
        </Button>
      </View>
    )
  }

  return (
    <View className='page game-session-page hainan-game-page'>
      <Text className='title'>游戏训练</Text>
      <Text className='error'>当前训练状态异常，请返回当前处方重新进入</Text>
    </View>
  )
}
