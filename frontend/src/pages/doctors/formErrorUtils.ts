import { isAxiosError } from "axios";

export type BackendFieldErrors = Record<string, string[]>;

function responseData(err: unknown): unknown {
  if (isAxiosError(err)) return err.response?.data;
  if (!err || typeof err !== "object" || !("response" in err)) return null;
  const response = (err as { response?: unknown }).response;
  if (!response || typeof response !== "object" || !("data" in response)) return null;
  return (response as { data?: unknown }).data;
}

function normalizeErrorValue(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value === "string") return value ? [value] : [];
  if (value == null) return [];
  return [JSON.stringify(value)];
}

export function extractBackendFieldErrors(err: unknown): BackendFieldErrors | null {
  const data = responseData(err);
  if (!data) return null;

  if (typeof data === "string" || Array.isArray(data)) {
    const detail = normalizeErrorValue(data);
    return detail.length ? { detail } : null;
  }
  if (typeof data !== "object") return null;

  const errors = Object.entries(data as Record<string, unknown>).reduce<BackendFieldErrors>((acc, [key, value]) => {
    const messages = normalizeErrorValue(value);
    if (messages.length) acc[key] = messages;
    return acc;
  }, {});

  return Object.keys(errors).length ? errors : null;
}

export function fieldErrorsToFormFields<FieldName extends string>(
  errors: BackendFieldErrors | null,
  allowedFields: readonly FieldName[],
): Array<{ name: FieldName; errors: string[] }> {
  if (!errors) return [];
  return allowedFields.flatMap((field) => {
    const messages = errors[field];
    return messages?.length ? [{ name: field, errors: messages }] : [];
  });
}

export function backendErrorsToMessage(errors: BackendFieldErrors | null): string | null {
  if (!errors) return null;
  const parts = Object.entries(errors).map(([key, value]) => `${key}: ${value.join(", ")}`);
  return parts.length ? parts.join("；") : null;
}
