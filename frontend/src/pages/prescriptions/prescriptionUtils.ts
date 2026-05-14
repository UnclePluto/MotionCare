import type { ActionParameterMode } from "./types";

export function getActionParameterMode(actionType: string): ActionParameterMode {
  return actionType === "有氧训练" ? "duration" : "count";
}
