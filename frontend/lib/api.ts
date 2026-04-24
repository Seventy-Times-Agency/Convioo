/**
 * Thin client around the FastAPI backend on Railway.
 *
 * Auth model (internal-use stage):
 *
 *   No API key, no password. User types their name, we hash it to a
 *   stable positive integer, store `{displayName, userId}` in local
 *   storage. The backend runs in "open mode" unless WEB_API_KEY is
 *   set in Railway — then this module auto-forwards the saved key.
 *
 * Real per-user auth (magic link + server session) lands when public
 * sign-up opens. Until then the backend trusts the caller to pick a
 * user id the way the bot trusts Telegram to supply one.
 */

export type SearchStatus = "pending" | "running" | "done" | "failed";

export interface SearchSummary {
  id: string;
  user_id: number;
  niche: string;
  region: string;
  status: SearchStatus;
  created_at: string;
  finished_at: string | null;
  leads_count: number;
  avg_score: number | null;
  hot_leads_count: number | null;
  error: string | null;
  insights?: string | null;
}

export interface LeadOut {
  id: string;
  name: string;
  website: string | null;
  phone: string | null;
  address: string | null;
  category: string | null;
  rating: number | null;
  reviews_count: number | null;
  latitude: number | null;
  longitude: number | null;
  enriched: boolean;
  score_ai: number | null;
  tags: string[] | null;
  summary: string | null;
  advice: string | null;
  strengths: string[] | null;
  weaknesses: string[] | null;
  red_flags: string[] | null;
  social_links: Record<string, string> | null;
  reviews_summary: string | null;
}

export interface SearchDetail extends SearchSummary {
  stats: Record<string, number> | null;
  leads: LeadOut[];
}

export interface SearchCreatePayload {
  user_id: number;
  niche: string;
  region: string;
  language_code?: string | null;
  display_name?: string | null;
  profession?: string | null;
}

export interface SearchCreateResponse {
  id: string;
  queued: boolean;
  running: boolean;
}

export interface ApiError {
  status: number;
  detail: string;
}

const STORAGE_KEY_USER = "leadgen.userId";
const STORAGE_KEY_NAME = "leadgen.displayName";
const STORAGE_KEY_PROF = "leadgen.profession";
// Optional: carried forward only if the site operator chose to set
// WEB_API_KEY on the backend. A blank key means open mode.
const STORAGE_KEY_API = "leadgen.apiKey";

// Hardcoded fallback so Vercel *preview* builds (which may not inherit
// production env vars) still reach the backend. Production deploys
// should still set NEXT_PUBLIC_API_URL explicitly — the fallback is a
// safety net, not the source of truth.
const DEFAULT_API_BASE = "https://leadgen-production-6758.up.railway.app";

export function getApiBase(): string {
  const url = process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE;
  return url.replace(/\/$/, "");
}

export interface AuthCreds {
  userId: number;
  displayName: string;
  profession?: string;
  apiKey?: string;
}

export function readAuth(): AuthCreds | null {
  if (typeof window === "undefined") return null;
  const userIdRaw = window.localStorage.getItem(STORAGE_KEY_USER);
  const name = window.localStorage.getItem(STORAGE_KEY_NAME);
  if (!userIdRaw || !name) return null;
  const userId = Number.parseInt(userIdRaw, 10);
  if (!Number.isFinite(userId)) return null;
  return {
    userId,
    displayName: name,
    profession: window.localStorage.getItem(STORAGE_KEY_PROF) ?? undefined,
    apiKey: window.localStorage.getItem(STORAGE_KEY_API) ?? undefined,
  };
}

export function writeAuth(creds: AuthCreds): void {
  window.localStorage.setItem(STORAGE_KEY_USER, String(creds.userId));
  window.localStorage.setItem(STORAGE_KEY_NAME, creds.displayName);
  if (creds.profession) {
    window.localStorage.setItem(STORAGE_KEY_PROF, creds.profession);
  } else {
    window.localStorage.removeItem(STORAGE_KEY_PROF);
  }
  if (creds.apiKey) {
    window.localStorage.setItem(STORAGE_KEY_API, creds.apiKey);
  } else {
    window.localStorage.removeItem(STORAGE_KEY_API);
  }
}

export function clearAuth(): void {
  window.localStorage.removeItem(STORAGE_KEY_USER);
  window.localStorage.removeItem(STORAGE_KEY_NAME);
  window.localStorage.removeItem(STORAGE_KEY_PROF);
  window.localStorage.removeItem(STORAGE_KEY_API);
}

/**
 * Stable positive 31-bit integer derived from a string. Used to turn a
 * display name into a user id that survives reloads and sign-outs so
 * the same person keeps their search history between sessions without
 * anyone having to type a number.
 */
export function nameToUserId(name: string): number {
  const s = name.trim().toLowerCase();
  // FNV-1a 32-bit hash, folded into the positive half so SQL BIGINT is
  // happy and no leading minus sign sneaks into any UI.
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h & 0x7fffffff;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const creds = readAuth();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (creds?.apiKey) {
    headers.set("X-API-Key", creds.apiKey);
  }
  const url = `${getApiBase()}${path}`;
  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (e) {
    // Network / CORS / DNS failure — fetch throws TypeError. Normalize
    // so UI can show something actionable instead of "Failed to fetch".
    const message = e instanceof Error ? e.message : String(e);
    const err: ApiError = {
      status: 0,
      detail: `Could not reach ${url} — ${message}`,
    };
    throw err;
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    const err: ApiError = { status: res.status, detail };
    throw err;
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("application/json")) {
    return (await res.text()) as unknown as T;
  }
  return (await res.json()) as T;
}

export async function pingHealth(): Promise<{
  status: string;
  db: boolean;
  commit: string;
}> {
  const res = await fetch(`${getApiBase()}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json();
}

export async function listSearches(
  creds: AuthCreds,
  limit = 20
): Promise<SearchSummary[]> {
  const params = new URLSearchParams({
    user_id: String(creds.userId),
    limit: String(limit),
  });
  return request<SearchSummary[]>(`/api/v1/searches?${params}`);
}

export async function createSearch(
  creds: AuthCreds,
  payload: Omit<SearchCreatePayload, "user_id">
): Promise<SearchCreateResponse> {
  const body: SearchCreatePayload = {
    user_id: creds.userId,
    display_name: creds.displayName,
    profession: creds.profession ?? null,
    ...payload,
  };
  return request<SearchCreateResponse>("/api/v1/searches", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function getSearch(
  _creds: AuthCreds,
  id: string
): Promise<SearchDetail> {
  return request<SearchDetail>(`/api/v1/searches/${id}`);
}

export async function getSearchLeads(
  _creds: AuthCreds,
  id: string
): Promise<LeadOut[]> {
  return request<LeadOut[]>(`/api/v1/searches/${id}/leads`);
}

export async function downloadExcel(
  creds: AuthCreds,
  id: string,
  filename: string
): Promise<void> {
  const headers: Record<string, string> = {};
  if (creds.apiKey) headers["X-API-Key"] = creds.apiKey;
  const res = await fetch(`${getApiBase()}/api/v1/searches/${id}/excel`, {
    headers,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw { status: res.status, detail } as ApiError;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export interface ProgressEvent {
  kind: "phase" | "update" | "finish" | "done";
  title?: string;
  subtitle?: string;
  done?: number;
  total?: number;
  text?: string;
}

export function progressUrl(creds: AuthCreds, id: string): string {
  const params = new URLSearchParams();
  if (creds.apiKey) params.set("api_key", creds.apiKey);
  const qs = params.toString();
  return `${getApiBase()}/api/v1/searches/${id}/progress${qs ? `?${qs}` : ""}`;
}

export function subscribeProgress(
  creds: AuthCreds,
  id: string,
  handlers: {
    onPhase?: (title: string, subtitle: string) => void;
    onUpdate?: (done: number, total: number) => void;
    onFinish?: (text: string) => void;
    onDone?: () => void;
    onError?: (err: Event) => void;
  }
): () => void {
  const src = new EventSource(progressUrl(creds, id));
  src.addEventListener("phase", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    handlers.onPhase?.(data.title ?? "", data.subtitle ?? "");
  });
  src.addEventListener("update", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    handlers.onUpdate?.(data.done ?? 0, data.total ?? 0);
  });
  src.addEventListener("finish", (e) => {
    const data = JSON.parse((e as MessageEvent).data);
    handlers.onFinish?.(data.text ?? "");
  });
  src.addEventListener("done", () => {
    handlers.onDone?.();
    src.close();
  });
  src.onerror = (e) => {
    handlers.onError?.(e);
  };
  return () => src.close();
}
