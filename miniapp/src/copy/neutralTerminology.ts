export const NEUTRAL_TERM_REPLACEMENTS = [
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

export function neutralizeMiniappMessage(message: string): string {
  return NEUTRAL_TERM_REPLACEMENTS.reduce(
    (result, [source, target]) => result.replaceAll(source, target),
    message,
  )
}
