import { apiClient } from "../../api/client";

export type TrainingExportRequest = {
  project_patient: number;
  range: "7d" | "30d" | "custom" | "all";
  start_date?: string;
  end_date?: string;
};

const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const FALLBACK_FILENAME = "患者编号_训练明细.xlsx";
const SAFE_ERROR_MESSAGE = "导出失败，请稍后重试";

function headerValue(headers: unknown, name: string): string {
  if (!headers || typeof headers !== "object") return "";
  const record = headers as Record<string, unknown> & { get?: (key: string) => unknown };
  const direct = record[name] ?? record[name.toLowerCase()] ?? record[name.toUpperCase()];
  if (typeof direct === "string") return direct;
  const fromGetter = record.get?.(name);
  return typeof fromGetter === "string" ? fromGetter : "";
}

function containsSensitiveText(value: string) {
  return /https?:\/\//i.test(value) ||
    /signature|token|secret|credential|authorization|raw response|access[_-]?key/i.test(value) ||
    /\b(?:AK|SK)\b\s*[:=]/.test(value);
}

function safeFilename(contentDisposition: string): string {
  const encodedMatch = contentDisposition.match(/filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i);
  const plainMatch = contentDisposition.match(/filename\s*=\s*(?:"([^"]*)"|([^;]+))/i);
  const raw = encodedMatch?.[1]?.trim().replace(/^"|"$/g, "") ?? plainMatch?.[1] ?? plainMatch?.[2]?.trim();
  if (!raw) return FALLBACK_FILENAME;

  try {
    const decoded = encodedMatch ? decodeURIComponent(raw) : raw;
    const sanitized = Array.from(decoded, (character) => {
      const code = character.charCodeAt(0);
      return character === "/" || character === "\\" || code < 32 || code === 127 ? "_" : character;
    }).join("").trim();
    return sanitized && sanitized.toLowerCase().endsWith(".xlsx") ? sanitized : FALLBACK_FILENAME;
  } catch {
    return FALLBACK_FILENAME;
  }
}

async function errorFromResponse(error: unknown): Promise<Error> {
  if (!error || typeof error !== "object" || !("response" in error)) return new Error(SAFE_ERROR_MESSAGE);
  const response = (error as { response?: { headers?: unknown; data?: unknown } }).response;
  const contentType = headerValue(response?.headers, "content-type").toLowerCase();
  if (!contentType.includes("application/json") || !(response?.data instanceof Blob)) {
    return new Error(SAFE_ERROR_MESSAGE);
  }

  try {
    const parsed = JSON.parse(await response.data.text()) as { detail?: unknown };
    const detail = typeof parsed.detail === "string" ? parsed.detail.trim() : "";
    if (detail && !containsSensitiveText(detail)) return new Error(detail);
  } catch {
    // Malformed or unreadable error bodies use the fixed safe message below.
  }
  return new Error(SAFE_ERROR_MESSAGE);
}

export async function downloadTrainingDetail(patientId: number, request: TrainingExportRequest): Promise<void> {
  let objectUrl: string | null = null;
  let anchor: HTMLAnchorElement | null = null;

  try {
    const response = await apiClient.post<Blob>(
      `/training/tracking/patients/${patientId}/export/`,
      request,
      { responseType: "blob", timeout: 75_000 },
    );
    const contentType = headerValue(response.headers, "content-type").split(";", 1)[0].trim().toLowerCase();
    if (!(response.data instanceof Blob) || response.data.size === 0 || contentType !== XLSX_MIME) {
      throw new Error(SAFE_ERROR_MESSAGE);
    }

    objectUrl = URL.createObjectURL(response.data);
    anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = safeFilename(headerValue(response.headers, "content-disposition"));
    anchor.hidden = true;
    document.body.appendChild(anchor);
    anchor.click();
  } catch (error) {
    if (error instanceof Error && error.message === SAFE_ERROR_MESSAGE) throw error;
    throw await errorFromResponse(error);
  } finally {
    if (objectUrl || anchor) {
      const createdUrl = objectUrl;
      const createdAnchor = anchor;
      window.setTimeout(() => {
        createdAnchor?.remove();
        if (createdUrl) URL.revokeObjectURL(createdUrl);
      }, 0);
    }
  }
}
