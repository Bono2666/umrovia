import { type ProblemDetail } from "./api";

function firstMessage(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") return firstMessage(Object.values(value)[0]);
  return "Periksa kembali isian formulir.";
}

export function formErrors(problem: ProblemDetail): Record<string, string> {
  const fields = Object.fromEntries(Object.entries(problem.field_errors ?? {}).map(([key, values]) => [key, firstMessage(values)]));
  return {...fields, form: Object.values(fields)[0] ?? problem.detail ?? "Periksa kembali isian formulir."};
}

/** Send only edited fields so unrelated values are retained by PATCH. */
export function changedFields<T extends object>(values: T, original: object): Partial<T> {
  const previous = original as Record<string, unknown>;
  return Object.fromEntries(Object.entries(values).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(previous[key]))) as Partial<T>;
}

export function focusForm(id: string) {
  requestAnimationFrame(() => {
    const form = document.getElementById(id);
    form?.scrollIntoView({behavior:"smooth", block:"start"});
    form?.querySelector<HTMLElement>("input:not(:disabled),select:not(:disabled),textarea:not(:disabled)")?.focus({preventScroll:true});
  });
}

/** datetime-local uses browser-local time; preserve the instant on save. */
export function localDateTime(iso: string | null): string {
  if (!iso) return "";
  const value = new Date(iso);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}
