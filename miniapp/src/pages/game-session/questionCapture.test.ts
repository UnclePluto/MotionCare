import { describe, expect, it } from 'vitest'

import { createQuestionCapture } from './questionCapture'

describe('question capture', () => {
  it('只累计可作答区间并丢弃未判定题', () => {
    let now = 0
    const capture = createQuestionCapture(() => now)
    capture.begin('game-executive-inhibition', '中等')
    now = 1200
    capture.pause()
    now = 9200
    capture.resume()
    now = 10500

    expect(capture.finish(true, 'answered')?.response_duration_ms).toBe(2500)

    capture.begin('game-executive-inhibition', '中等')
    capture.discard()
    expect(capture.results()).toHaveLength(1)
    expect(capture.results()[0].question_index).toBe(1)
    capture.begin('game-executive-inhibition', '中等')
    now = 10600
    expect(capture.finish(true, 'answered')).toMatchObject({question_index: 2, response_duration_ms: 100})
  })

  it('重复暂停和恢复不会重复结算或重置计时起点', () => {
    let now = 0
    const capture = createQuestionCapture(() => now)
    capture.begin('game-memory-color-sequence', '简单')
    now = 100
    capture.pause()
    now = 500
    capture.pause()
    now = 1000
    capture.resume()
    now = 1500
    capture.resume()
    now = 2000

    expect(capture.finish(false, 'timeout')?.response_duration_ms).toBe(1100)
    expect(capture.finish(false, 'timeout')).toBeNull()
  })

  it('未开始题目时不产生判定结果', () => {
    const capture = createQuestionCapture(() => 0)

    expect(capture.finish(true, 'answered')).toBeNull()
    expect(capture.results()).toEqual([])
  })

  it('返回结果与内部结果互相隔离', () => {
    let now = 10
    const capture = createQuestionCapture(() => now)
    capture.begin('game-executive-category-switch', '困难')
    now = 20
    const finished = capture.finish(true, 'answered')
    if (!finished) throw new Error('预期生成题目结果')
    finished.response_duration_ms = 999

    const firstRead = capture.results()
    firstRead[0].difficulty = '简单'
    firstRead.push({ ...firstRead[0], question_index: 2 })

    expect(capture.results()).toEqual([{
      capture_version: 'active_response_v2', expected_step_count: null, selection_steps: [], click_count: null,
      question_index: 1,
      game_code: 'game-executive-category-switch',
      difficulty: '困难',
      response_duration_ms: 10,
      is_correct: true,
      result_type: 'answered',
      swap_count: null,
    }])
  })

  it('只为拼图题记录交换次数并在新题开始时清零', () => {
    let now = 0
    const capture = createQuestionCapture(() => now)
    capture.begin('game-audiovisual-puzzle', '中等')
    capture.recordSwap()
    capture.recordSwap()
    now = 1

    expect(capture.finish(true, 'answered')?.swap_count).toBe(2)

    capture.begin('game-executive-inhibition', '中等')
    capture.recordSwap()
    now = 2
    expect(capture.finish(true, 'answered')?.swap_count).toBeNull()
  })

  it('拒绝回拨和非有限时钟输入', () => {
    let now = 100
    const capture = createQuestionCapture(() => now)
    capture.begin('game-executive-inhibition', '中等')
    now = 99
    expect(() => capture.pause()).toThrow('作答时钟无效')

    now = Number.NaN
    expect(() => capture.pause()).toThrow('作答时钟无效')
  })

  it('reset清空当前题和已判定结果', () => {
    let now = 0
    const capture = createQuestionCapture(() => now)
    capture.begin('game-audiovisual-sound-discrimination', '简单')
    now = 10
    capture.finish(true, 'answered')
    capture.begin('game-audiovisual-sound-discrimination', '简单')

    capture.reset()

    expect(capture.finish(true, 'answered')).toBeNull()
    expect(capture.results()).toEqual([])
  })
})

it('逐步保留错选与暂停，累计取整后差分，结束半题幂等且结果深拷贝', () => {
  let now = 0
  const capture = createQuestionCapture(() => now)
  capture.begin('game-memory-color-sequence', '简单')
  now = 100.4
  capture.recordSelection('green', 'blue')
  now = 150.6
  capture.pause()
  now = 8150.6
  capture.resume()
  now = 8200.8
  capture.recordSelection('yellow', 'yellow')
  const result = capture.finish(false, 'interrupted')!
  expect(result).toMatchObject({capture_version: 'active_response_v2', expected_step_count: 3, response_duration_ms: 201, result_type: 'interrupted', click_count: null})
  expect(result.selection_steps).toEqual([
    {step_index: 1, selected_value: 'green', expected_value: 'blue', response_duration_ms: 100, is_correct: false},
    {step_index: 2, selected_value: 'yellow', expected_value: 'yellow', response_duration_ms: 101, is_correct: true},
  ])
  result.selection_steps![0].selected_value = 'red'
  capture.results()[0].selection_steps![0].is_correct = true
  expect(capture.results()[0].selection_steps![0]).toMatchObject({selected_value: 'green', is_correct: false})
  expect(capture.finish(false, 'interrupted')).toBeNull()
  capture.begin('game-memory-color-sequence', '简单')
  expect(capture.finish(false, 'interrupted')).toBeNull()
  expect(capture.results()).toHaveLength(1)
})

it('拼图点击与交换分开计数且暂停禁记，顺序超时保留步骤', () => {
  const capture = createQuestionCapture(() => 0)
  capture.begin('game-audiovisual-puzzle', '简单')
  capture.recordClick(); capture.recordClick(); capture.recordClick(); capture.recordClick()
  capture.recordSwap()
  capture.pause(); capture.recordClick()
  expect(capture.finish(true, 'answered')).toMatchObject({click_count: 4, swap_count: 1, expected_step_count: null, selection_steps: []})
  capture.begin('game-memory-pattern-sequence', '中等')
  capture.recordSelection('sun', 'boat')
  expect(capture.finish(false, 'timeout')).toMatchObject({expected_step_count: 4, selection_steps: [{step_index: 1, is_correct: false}]})
})
