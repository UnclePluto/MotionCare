export type ProjectPatientLite = { project: number };

export function buildPatientDeleteModalCopy(
  projectPatients: ProjectPatientLite[],
  projectNameById: Record<number, string>,
): { blocked: string | null; summary: string[] } {
  if (projectPatients.length > 0) {
    const names = projectPatients
      .map((r) => projectNameById[r.project] ?? `项目 #${r.project}`)
      .join("、");
    return {
      blocked: `该患者仍关联 ${projectPatients.length} 个研究项目，系统禁止物理删除。请先在各项目看板「解绑」或改用「停用档案」。关联项目：${names}`,
      summary: [],
    };
  }
  return {
    blocked: null,
    summary: [
      "将永久删除该患者档案及本地可恢复副本（若存在），且不可恢复。",
      "当前未检测到研究项目入组关联。",
    ],
  };
}
