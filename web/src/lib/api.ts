/* Typed client for the Bizzmind FastAPI backend.
   Same-origin (Next.js rewrites /api → FastAPI), cookies carry the Supabase
   session, so no tokens are handled here. */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let loggingOut = false;
export function beginLogout() { loggingOut = true; }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(init?.headers ?? {}) },
    credentials: "same-origin",
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined" && !loggingOut && !location.pathname.startsWith("/login")) {
    location.href = "/login?next=" + encodeURIComponent(location.pathname);
  }
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text.slice(0, 200) }; }
  if (!res.ok) {
    const d = data as { detail?: string } | null;
    throw new ApiError(res.status, d?.detail ?? `HTTP ${res.status}`);
  }
  return data as T;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

/* ---------------------------------------------------------------- types */

export interface Me { email: string; id: string; orgs: string[]; roles: Record<string, string> }

export interface ProjectCard {
  id: string; name: string; created: string; tables: number; charts: number; notes: number;
}

export type ChartType = "bar" | "line" | "area" | "pie" | "scatter" | "table";

export interface Chart {
  id: number;
  title: string;
  insight: string;
  chart_type: ChartType;
  x_field: string;
  y_fields: string[];
  rows: Record<string, unknown>[];
  error?: string;
  filters?: string[];
}

export interface Filter {
  id: string; label: string; type: "multi" | "single"; column: string;
  options?: string[]; resolved_options: string[];
}

export interface TableInfo {
  table: string; kind: "table" | "view"; rows: number;
  columns: { name: string; type: string }[]; sample_rows: Record<string, unknown>[]; description?: string;
}

export interface ChatMessage {
  role: "user" | "ai" | "event" | "process";
  text: string; ts?: string;
  questions?: Question[];
}

export interface Question { question: string; options: string[]; multi?: boolean }

export interface I18nInfo {
  content_lang: string; ui_lang: string; needs_translation: boolean; missing?: number;
  field_labels: Record<string, string>; value_labels: Record<string, string>;
}

export interface ProjectState {
  name: string;
  tables: TableInfo[];
  charts: Chart[];
  notes: string[];
  filters: Filter[];
  chat: ChatMessage[];
  brand: string[];
  brand_theme: { primary: string; accent: string };
  brand_logo: string | null;
  brand_colors: string[];
  brand_fonts: string[];
  files: { filename: string; tables: string[] }[];
  i18n: I18nInfo;
}

export interface RefreshResponse { charts: Chart[]; filters: Filter[]; i18n: I18nInfo }

export interface TableRows {
  total: number; offset: number; limit: number;
  columns: { name: string; type: string }[];
  rows: Record<string, unknown>[];
}

export interface JobEvent { seq: number; kind: string; text: string; ts: string }
export interface JobStatus<T = unknown> {
  id: string; kind: string; status: "queued" | "running" | "done" | "failed";
  error: string | null; result: T | null; events: JobEvent[];
}

export interface AgentResult {
  reply: string; charts: number[]; questions?: Question[];
}

/* ---------------------------------------------------------------- endpoints */

export const p = (pid: string, path: string) => `/api/p/${encodeURIComponent(pid)}${path}`;

export const endpoints = {
  me: () => api<Me>("/api/auth/me"),
  login: (email: string, password: string) => post<{ ok: boolean; email: string }>("/api/auth/login", { email, password }),
  register: (email: string, password: string, name: string) =>
    post<{ ok: boolean; confirmed: boolean; message?: string }>("/api/auth/register",
      { email, password, name, redirect: typeof window !== "undefined" ? window.location.origin : "" }),
  logout: () => post<{ ok: boolean }>("/api/auth/logout"),
  projects: () => api<{ projects: ProjectCard[] }>("/api/projects"),
  createProject: (name: string) => post<{ id: string; name: string }>("/api/projects", { name }),
  deleteProject: (pid: string) => del<{ ok: boolean }>(`/api/projects/${encodeURIComponent(pid)}`),
  state: (pid: string) => api<ProjectState>(p(pid, "/state")),
  refresh: (pid: string, selections: Record<string, string[] | string>) =>
    post<RefreshResponse>(p(pid, "/dashboard/refresh"), { selections }),
  rows: (pid: string, table: string, q: URLSearchParams) =>
    api<TableRows>(p(pid, `/table/${encodeURIComponent(table)}/rows?${q.toString()}`)),
  job: <T,>(id: string, since = 0) => api<JobStatus<T>>(`/api/jobs/${id}?since=${since}`),
  chat: (pid: string, message: string) => post<{ job_id: string } | AgentResult>(p(pid, "/chat"), { message }),
  review: (pid: string, tables: string[], context: string, goal: string) =>
    post<{ job_id: string } | AgentResult>(p(pid, "/review"), { tables, context, goal }),
  translate: (pid: string) => post<{ job_id?: string; translated?: number }>(p(pid, "/translate")),
  addNote: (pid: string, note: string) => post<{ notes: string[] }>(p(pid, "/notes"), { note }),
  deleteFile: (pid: string, filename: string) => del<{ ok: boolean }>(p(pid, `/files/${encodeURIComponent(filename)}`)),
  reset: (pid: string) => post<{ ok: boolean }>(p(pid, "/reset")),
};

/* Run a background job: POST → {job_id} → poll until done. Inline results
   (INLINE_JOBS) come back directly. */
export async function runJob<T>(
  start: Promise<{ job_id: string } | T>,
  onEvent?: (ev: JobEvent) => void,
  signal?: AbortSignal,
): Promise<T> {
  const first = await start;
  if (!first || typeof first !== "object" || !("job_id" in first)) return first as T;
  const id = (first as { job_id: string }).job_id;
  // serverless worker: this request runs the job and stays open until it ends;
  // a dedicated worker (local dev) may claim it first — then it's a no-op
  fetch(`/api/jobs/${id}/run`, { method: "POST", credentials: "same-origin", keepalive: true }).catch(() => {});
  let since = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, 1200));
    if (signal?.aborted) throw new Error("cancelled");
    const j = await endpoints.job<T>(id, since);
    for (const ev of j.events) { since = ev.seq; onEvent?.(ev); }
    if (j.status === "done") return (j.result ?? {}) as T;
    if (j.status === "failed") throw new Error(j.error ?? "job failed");
  }
}


/* ------------------------------------------------ small local cache (perceived speed)
   Last successful responses are kept in localStorage and used as placeholder
   data while the fresh request is in flight. Never a source of truth. */
export function cacheGet<T>(key: string): T | undefined {
  try { const raw = localStorage.getItem("bz:" + key); return raw ? (JSON.parse(raw) as T) : undefined; } catch { return undefined; }
}
export function cacheSet(key: string, value: unknown) {
  try { localStorage.setItem("bz:" + key, JSON.stringify(value)); } catch { /* quota / private mode */ }
}
