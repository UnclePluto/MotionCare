import { describe, expect, it } from 'vitest'

import { neutralizeMiniappMessage } from './neutralTerminology'

describe('中性术语转换器', () => {
  const cases = [
    ['患者', '用户'],
    ['病人', '用户'],
    ['医生', '指导老师'],
    ['医护', '指导老师'],
    ['处方', '运动计划'],
    ['康复', '运动'],
    ['医疗', '运动服务'],
    ['诊疗', '运动指导'],
    ['医嘱', '运动说明'],
    ['治疗', '训练'],
    ['医院', '服务机构'],
    ['疾病', '身体情况'],
  ] as const

  it.each(cases)('replaces %s with %s', (source, target) => {
    expect(neutralizeMiniappMessage(`提示：${source}`)).toBe(`提示：${target}`)
  })

  it('keeps neutral text unchanged', () => {
    expect(neutralizeMiniappMessage('训练记录上传失败')).toBe('训练记录上传失败')
  })
})
