/**
 * Thin client for the Convioo backend.
 *
 * Requests are sent same-origin (``/api/...``) and rewritten to the
 * Railway service by ``next.config.js``. ``credentials: 'include'``
 * keeps the auth cookie attached on every call. Types mirror
 * src/leadgen/adapters/web_api/schemas.py — keep them in sync by
 * convention; we'll codegen from the OpenAPI schema later.
 */

import { getCurrentUser, type CurrentUser } from "./auth";

const RAW_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const API_BASE = RAW_BASE.replace(/\/$/, "");

function requireUserId(): number {
  const u = getCurrentUser();
  if (!u) {
    throw new ApiError("Not signed in", 401, null);
  }
  return u.user_id;
}

// ── Types ───────────────────────────────────────────────────────────

export type SearchStatus = "pending" | "running" | "done" | "failed";
export type LeadTemp = "hot" | "warm" | "cold";
export type LeadStatus = "new" | "contacted" | "replied" | "won" | "archived";

export interface SearchSummary {
  id: string;
  user_id: number;
  niche: string;
  region: string;
  status: SearchStatus;
  source: string;
  created_at: string;
  finished_at: string | null;
  leads_count: number;
  avg_score: number | null;
  hot_leads_count: number | null;
  error: string | null;
  insights: string | null;
}

export interface SearchCreate {
  niche: string;
  region: string;
  user_id?: number;
  language_code?: string;
  /** Optional list of BCP-47 language codes the lead must operate in. */
  target_languages?: string[];
  profession?: string;
  /** Per-search lead cap (5 / 10 / 20 / 30 / 50). */
  limit?: number;
  /** Geo shape: city / metro / state / country. Default city. */
  scope?: SearchScope;
  /** Radius in kilometres. Only meaningful when scope ∈ {city, metro}. */
  radius_km?: number;
}

export const LEAD_LIMIT_CHOICES = [5, 10, 20, 30, 50] as const;
export type LeadLimitChoice = (typeof LEAD_LIMIT_CHOICES)[number];
export const DEFAULT_LEAD_LIMIT: LeadLimitChoice = 50;

export const SEARCH_SCOPES = ["city", "metro", "state", "country"] as const;
export type SearchScope = (typeof SEARCH_SCOPES)[number];
export const RADIUS_CHOICES_KM = [5, 10, 25, 50, 100] as const;
export type RadiusChoiceKm = (typeof RADIUS_CHOICES_KM)[number];

export interface CityEntry {
  id: string;
  name: string;
  country: string;
  lat: number;
  lon: number;
  population: number;
}

export async function listCities(args: {
  q?: string | null;
  country?: string | null;
  lang?: string | null;
  limit?: number;
} = {}): Promise<{ items: CityEntry[]; query: string; language: string }> {
  const params = new URLSearchParams();
  if (args.q) params.set("q", args.q);
  if (args.country) params.set("country", args.country);
  if (args.lang) params.set("lang", args.lang);
  if (args.limit) params.set("limit", String(args.limit));
  const qs = params.toString();
  return request<{ items: CityEntry[]; query: string; language: string }>(
    `/api/v1/cities${qs ? "?" + qs : ""}`,
  );
}

export interface SearchCreateResponse {
  id: string;
  queued: boolean;
}

export interface LeadTag {
  id: string;
  name: string;
  color: string;
  team_id: string | null;
}

export interface Lead {
  id: string;
  query_id: string;
  name: string;
  category: string | null;
  address: string | null;
  phone: string | null;
  website: string | null;
  rating: number | null;
  reviews_count: number | null;
  score_ai: number | null;
  tags: string[] | null;
  summary: string | null;
  advice: string | null;
  strengths: string[] | null;
  weaknesses: string[] | null;
  red_flags: string[] | null;
  social_links: Record<string, string> | null;
  lead_status: LeadStatus;
  owner_user_id: number | null;
  notes: string | null;
  last_touched_at: string | null;
  mark_color: string | null;
  user_tags: LeadTag[];
  created_at: string;
}

/** Personal colour palette for lead marks. Add to / reorder freely;
 *  the backend stores whatever short token the picker sends. */
export const LEAD_MARK_COLORS = [
  "red",
  "orange",
  "yellow",
  "green",
  "teal",
  "blue",
  "violet",
  "pink",
] as const;
export type LeadMarkColor = (typeof LEAD_MARK_COLORS)[number];

export const LEAD_MARK_HEX: Record<LeadMarkColor, string> = {
  red: "#EF4444",
  orange: "#F97316",
  yellow: "#EAB308",
  green: "#16A34A",
  teal: "#14B8A6",
  blue: "#3B82F6",
  violet: "#8B5CF6",
  pink: "#EC4899",
};

export function leadMarkHex(color: string | null | undefined): string | null {
  if (!color) return null;
  return (LEAD_MARK_HEX as Record<string, string>)[color] ?? null;
}

export interface TeamMemberSummary {
  user_id: number;
  name: string;
  role: string;
  sessions_total: number;
  leads_total: number;
  hot_total: number;
}

export interface LeadListResponse {
  leads: Lead[];
  total: number;
  sessions_by_id: Record<string, { niche: string; region: string }>;
}

export interface LeadUpdate {
  lead_status?: LeadStatus;
  owner_user_id?: number | null;
  notes?: string | null;
}

export interface DashboardStats {
  sessions_total: number;
  sessions_running: number;
  leads_total: number;
  hot_total: number;
  warm_total: number;
  cold_total: number;
}

export interface TeamMember {
  id: number;
  name: string;
  role: string;
  description: string | null;
  initials: string;
  color: string;
  email: string | null;
  last_active: string | null;
}

export interface UserProfile {
  user_id: number;
  first_name: string;
  last_name: string;
  display_name: string | null;
  age_range: string | null;
  gender: string | null;
  business_size: string | null;
  profession: string | null;
  service_description: string | null;
  home_region: string | null;
  niches: string[] | null;
  language_code: string | null;
  onboarded: boolean;
  email: string | null;
  email_verified: boolean;
  recovery_email_masked: string | null;
  queries_used: number;
  queries_limit: number;
}

export interface UserProfileUpdate {
  display_name?: string | null;
  age_range?: string | null;
  gender?: string | null;
  business_size?: string | null;
  service_description?: string | null;
  home_region?: string | null;
  niches?: string[] | null;
  language_code?: string | null;
}

export interface TeamSummary {
  id: string;
  name: string;
  plan: string;
  role: string;
  member_count: number;
  created_at: string;
}

export interface TeamDetail {
  id: string;
  name: string;
  description: string | null;
  plan: string;
  created_at: string;
  role: string;
  members: TeamMember[];
}

export interface InviteResponse {
  token: string;
  team_id: string;
  team_name: string;
  role: string;
  expires_at: string;
}

export interface InvitePreview {
  team_id: string;
  team_name: string;
  role: string;
  expires_at: string;
  expired: boolean;
  accepted: boolean;
}

// ── Fetch core ──────────────────────────────────────────────────────

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // Same-origin first: Next.js rewrites /api/* to the Railway service
  // so the auth cookie travels as first-party. Fallback to the raw
  // API base if rewrites are disabled (e.g. running the SPA standalone
  // without the rewrite layer).
  const target = path.startsWith("/api/") || path === "/health" || path === "/metrics"
    ? path
    : `${API_BASE}${path}`;
  const res = await fetch(target, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    credentials: "include",
    cache: "no-store",
  });
  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : null) ?? `${res.status} ${res.statusText}`;
    throw new ApiError(detail, res.status, body);
  }
  return body as T;
}

// ── Endpoints ───────────────────────────────────────────────────────

export interface AuthUser extends CurrentUser {
  email: string | null;
  email_verified: boolean;
  onboarded: boolean;
}

export const REFERRAL_COOKIE_NAME = "convioo_ref";

function readReferralCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split(";")
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${REFERRAL_COOKIE_NAME}=`));
  if (!match) return null;
  const value = decodeURIComponent(match.slice(REFERRAL_COOKIE_NAME.length + 1));
  return value || null;
}

export async function registerUser(args: {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  ageRange?: string | null;
  gender?: string | null;
  registrationPassword?: string | null;
}): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      first_name: args.firstName,
      last_name: args.lastName,
      email: args.email,
      password: args.password,
      age_range: args.ageRange ?? null,
      gender: args.gender ?? null,
      registration_password: args.registrationPassword ?? null,
      referral_code: readReferralCookie(),
    }),
  });
}

export async function loginUser(
  email: string,
  password: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function verifyEmail(token: string): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resendVerification(
  email: string,
): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>("/api/v1/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function changeEmail(
  newEmail: string,
  password: string,
): Promise<AuthUser> {
  return request<AuthUser>(
    `/api/v1/users/${requireUserId()}/change-email`,
    {
      method: "POST",
      body: JSON.stringify({ new_email: newEmail, password }),
    },
  );
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<AuthUser> {
  return request<AuthUser>(
    `/api/v1/users/${requireUserId()}/change-password`,
    {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
  );
}

// ── Account recovery & sessions ────────────────────────────────────

export async function fetchAuthMe(): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/me");
}

export async function logoutCurrentSession(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" });
}

export async function logoutAllSessions(): Promise<{ revoked: number }> {
  return request<{ revoked: number }>("/api/v1/auth/logout-all", {
    method: "POST",
  });
}

export async function forgotPassword(
  email: string,
): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function forgotEmail(
  recoveryEmail: string,
): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>("/api/v1/auth/forgot-email", {
    method: "POST",
    body: JSON.stringify({ recovery_email: recoveryEmail }),
  });
}

export async function setRecoveryEmail(
  recoveryEmail: string | null,
): Promise<UserProfile> {
  return request<UserProfile>("/api/v1/auth/recovery-email", {
    method: "PATCH",
    body: JSON.stringify({ recovery_email: recoveryEmail }),
  });
}

export interface SessionInfo {
  id: string;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export async function listMySessions(): Promise<{
  sessions: SessionInfo[];
  count: number;
}> {
  return request<{ sessions: SessionInfo[]; count: number }>(
    "/api/v1/auth/sessions",
  );
}

export async function revokeMySession(
  sessionId: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/auth/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function getMyProfile(userId?: number): Promise<UserProfile> {
  const id = userId ?? requireUserId();
  return request<UserProfile>(`/api/v1/users/${id}`);
}

export async function updateMyProfile(
  patch: UserProfileUpdate,
  userId?: number,
): Promise<UserProfile> {
  const id = userId ?? requireUserId();
  return request<UserProfile>(`/api/v1/users/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export interface AuditLogEntry {
  id: string;
  action: string;
  ip: string | null;
  user_agent: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export async function listAuditLog(
  userId?: number,
): Promise<{ items: AuditLogEntry[] }> {
  const id = userId ?? requireUserId();
  return request<{ items: AuditLogEntry[] }>(
    `/api/v1/users/${id}/audit-log`,
  );
}

export function gdprExportUrl(userId?: number): string {
  const id = userId ?? requireUserId();
  return `/api/v1/users/${id}/export`;
}

export function sessionXlsxUrl(sessionId: string): string {
  return `/api/v1/searches/${sessionId}/export.xlsx`;
}

export async function deleteAccount(args: {
  confirmEmail: string;
  password?: string;
  userId?: number;
}): Promise<{ deleted: boolean }> {
  const id = args.userId ?? requireUserId();
  return request<{ deleted: boolean }>(`/api/v1/users/${id}`, {
    method: "DELETE",
    body: JSON.stringify({
      confirm_email: args.confirmEmail,
      password: args.password,
    }),
  });
}

export interface ConsultMessage {
  role: "user" | "assistant";
  content: string;
}

export type ConsultSlot =
  | "niche"
  | "region"
  | "ideal_customer"
  | "exclusions";

export interface ConsultResponse {
  reply: string;
  niche: string | null;
  region: string | null;
  ideal_customer: string | null;
  exclusions: string | null;
  ready: boolean;
  last_asked_slot: ConsultSlot | null;
}

export interface ConsultCurrentState {
  niche?: string | null;
  region?: string | null;
  ideal_customer?: string | null;
  exclusions?: string | null;
  last_asked_slot?: ConsultSlot | null;
}

export async function consultSearch(
  messages: ConsultMessage[],
  currentState: ConsultCurrentState = {},
): Promise<ConsultResponse> {
  return request<ConsultResponse>("/api/v1/search/consult", {
    method: "POST",
    body: JSON.stringify({
      user_id: requireUserId(),
      messages,
      current_niche: currentState.niche ?? null,
      current_region: currentState.region ?? null,
      current_ideal_customer: currentState.ideal_customer ?? null,
      current_exclusions: currentState.exclusions ?? null,
      last_asked_slot: currentState.last_asked_slot ?? null,
    }),
  });
}

export type AssistantMode = "personal" | "team_member" | "team_owner";

export type AssistantField =
  | "display_name"
  | "age_range"
  | "business_size"
  | "service_description"
  | "home_region"
  | "niches";

export type PendingActionKind =
  | "profile_patch"
  | "team_description"
  | "member_description"
  | "launch_search";

export interface PendingAction {
  kind: PendingActionKind;
  summary: string;
  payload: Record<string, unknown>;
}

export interface AssistantResponse {
  reply: string;
  mode: AssistantMode;
  suggestion_summary: string | null;
  awaiting_field: AssistantField | null;
  pending_actions: PendingAction[] | null;
  applied_actions: PendingAction[] | null;
}

export async function assistantChat(
  messages: ConsultMessage[],
  opts: {
    teamId?: string;
    awaitingField?: AssistantField | null;
    pendingActions?: PendingAction[] | null;
  } = {},
): Promise<AssistantResponse> {
  return request<AssistantResponse>("/api/v1/assistant/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: requireUserId(),
      team_id: opts.teamId,
      messages,
      awaiting_field: opts.awaitingField ?? null,
      pending_actions: opts.pendingActions ?? null,
    }),
  });
}

// ── Henry memory transparency ──────────────────────────────────────

export type AssistantMemoryKind = "summary" | "fact";

export interface AssistantMemoryItem {
  id: string;
  kind: AssistantMemoryKind;
  content: string;
  team_id: string | null;
  created_at: string;
}

export async function listAssistantMemory(opts: { teamId?: string } = {}): Promise<{
  items: AssistantMemoryItem[];
}> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  const qs = params.toString();
  return request<{ items: AssistantMemoryItem[] }>(
    `/api/v1/users/${requireUserId()}/assistant-memory${qs ? `?${qs}` : ""}`,
  );
}

export async function clearAssistantMemory(opts: { teamId?: string } = {}): Promise<{
  deleted: number;
}> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  const qs = params.toString();
  return request<{ deleted: number }>(
    `/api/v1/users/${requireUserId()}/assistant-memory${qs ? `?${qs}` : ""}`,
    { method: "DELETE" },
  );
}

export async function suggestNiches(): Promise<{ suggestions: string[] }> {
  return request<{ suggestions: string[] }>(
    `/api/v1/users/${requireUserId()}/suggest-niches`,
    { method: "POST" },
  );
}

export interface WeeklyCheckin {
  summary: string;
  highlights: string[];
  leads_total: number;
  hot_total: number;
  new_this_week: number;
  untouched_14d: number;
  sessions_this_week: number;
}

export async function getWeeklyCheckin(
  opts: { teamId?: string; memberUserId?: number } = {},
): Promise<WeeklyCheckin> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  const qs = params.toString();
  return request<WeeklyCheckin>(
    `/api/v1/users/${requireUserId()}/weekly-checkin${qs ? `?${qs}` : ""}`,
  );
}

export interface OutreachTemplate {
  id: string;
  user_id: number;
  team_id: string | null;
  name: string;
  subject: string | null;
  body: string;
  tone: string;
  created_at: string;
  updated_at: string;
}

export async function listOutreachTemplates(opts: { teamId?: string } = {}): Promise<{
  items: OutreachTemplate[];
}> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  if (opts.teamId) params.set("team_id", opts.teamId);
  return request<{ items: OutreachTemplate[] }>(
    `/api/v1/templates?${params.toString()}`,
  );
}

export async function createOutreachTemplate(input: {
  name: string;
  subject?: string | null;
  body: string;
  tone?: string;
  teamId?: string;
}): Promise<OutreachTemplate> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<OutreachTemplate>(`/api/v1/templates?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      subject: input.subject ?? null,
      body: input.body,
      tone: input.tone ?? "professional",
      team_id: input.teamId ?? null,
    }),
  });
}

export async function updateOutreachTemplate(
  id: string,
  patch: { name?: string; subject?: string | null; body?: string; tone?: string },
): Promise<OutreachTemplate> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<OutreachTemplate>(
    `/api/v1/templates/${id}?${params.toString()}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export async function deleteOutreachTemplate(id: string): Promise<void> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  await request<{ deleted: boolean }>(
    `/api/v1/templates/${id}?${params.toString()}`,
    { method: "DELETE" },
  );
}

// ── Lead custom fields, activity, tasks ────────────────────────────

export interface LeadCustomField {
  id: string;
  lead_id: string;
  user_id: number;
  key: string;
  value: string | null;
  updated_at: string;
}

export async function listLeadCustomFields(
  leadId: string,
): Promise<{ items: LeadCustomField[] }> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<{ items: LeadCustomField[] }>(
    `/api/v1/leads/${leadId}/custom-fields?${params.toString()}`,
  );
}

export async function upsertLeadCustomField(
  leadId: string,
  key: string,
  value: string | null,
): Promise<LeadCustomField> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<LeadCustomField>(
    `/api/v1/leads/${leadId}/custom-fields?${params.toString()}`,
    {
      method: "PUT",
      body: JSON.stringify({ key, value }),
    },
  );
}

export async function deleteLeadCustomField(
  leadId: string,
  key: string,
): Promise<void> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  await request<{ deleted: boolean }>(
    `/api/v1/leads/${leadId}/custom-fields/${encodeURIComponent(key)}?${params.toString()}`,
    { method: "DELETE" },
  );
}

export type LeadActivityKind =
  | "status"
  | "notes"
  | "assigned"
  | "mark"
  | "custom_field"
  | "task"
  | "created";

export interface LeadActivity {
  id: string;
  lead_id: string;
  user_id: number;
  team_id: string | null;
  kind: LeadActivityKind;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export async function listLeadActivity(
  leadId: string,
): Promise<{ items: LeadActivity[] }> {
  return request<{ items: LeadActivity[] }>(
    `/api/v1/leads/${leadId}/activity`,
  );
}

export interface LeadTask {
  id: string;
  lead_id: string;
  user_id: number;
  content: string;
  due_at: string | null;
  done_at: string | null;
  created_at: string;
}

export async function listLeadTasks(
  leadId: string,
): Promise<{ items: LeadTask[] }> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<{ items: LeadTask[] }>(
    `/api/v1/leads/${leadId}/tasks?${params.toString()}`,
  );
}

export async function createLeadTask(
  leadId: string,
  content: string,
  dueAt?: Date | null,
): Promise<LeadTask> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<LeadTask>(
    `/api/v1/leads/${leadId}/tasks?${params.toString()}`,
    {
      method: "POST",
      body: JSON.stringify({
        content,
        due_at: dueAt ? dueAt.toISOString() : null,
      }),
    },
  );
}

export async function updateLeadTask(
  taskId: string,
  patch: { content?: string; due_at?: string | null; done?: boolean },
): Promise<LeadTask> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<LeadTask>(
    `/api/v1/tasks/${taskId}?${params.toString()}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export async function deleteLeadTask(taskId: string): Promise<void> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  await request<{ deleted: boolean }>(
    `/api/v1/tasks/${taskId}?${params.toString()}`,
    { method: "DELETE" },
  );
}

export async function listMyTasks(opts: { openOnly?: boolean } = {}): Promise<{
  items: LeadTask[];
}> {
  const params = new URLSearchParams();
  if (opts.openOnly !== undefined) params.set("open_only", String(opts.openOnly));
  const qs = params.toString();
  return request<{ items: LeadTask[] }>(
    `/api/v1/users/${requireUserId()}/tasks${qs ? `?${qs}` : ""}`,
  );
}

export interface SearchAxisOption {
  niche: string;
  region: string;
  ideal_customer: string | null;
  exclusions: string | null;
  rationale: string | null;
}

export async function suggestSearchAxes(): Promise<{
  options: SearchAxisOption[];
}> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<{ options: SearchAxisOption[] }>(
    `/api/v1/search/suggest-axes?${params.toString()}`,
    { method: "POST" },
  );
}

export async function updateTeam(
  teamId: string,
  patch: { name?: string; description?: string | null },
): Promise<TeamDetail> {
  return request<TeamDetail>(`/api/v1/teams/${teamId}`, {
    method: "PATCH",
    body: JSON.stringify({ by_user_id: requireUserId(), ...patch }),
  });
}

export async function updateTeamMember(
  teamId: string,
  memberUserId: number,
  patch: { description?: string | null; role?: string },
): Promise<TeamDetail> {
  return request<TeamDetail>(
    `/api/v1/teams/${teamId}/members/${memberUserId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ by_user_id: requireUserId(), ...patch }),
    },
  );
}

export interface PriorTeamSearch {
  search_id: string;
  user_id: number;
  user_name: string;
  niche: string;
  region: string;
  leads_count: number;
  created_at: string;
}

export interface SearchPreflightResponse {
  blocked: boolean;
  matches: PriorTeamSearch[];
}

export async function preflightSearch(args: {
  niche: string;
  region: string;
  teamId?: string;
}): Promise<SearchPreflightResponse> {
  const params = new URLSearchParams({
    user_id: String(requireUserId()),
    niche: args.niche,
    region: args.region,
  });
  if (args.teamId) params.set("team_id", args.teamId);
  return request<SearchPreflightResponse>(
    `/api/v1/searches/preflight?${params.toString()}`,
  );
}

export async function createSearch(
  body: SearchCreate & { team_id?: string },
): Promise<SearchCreateResponse> {
  return request<SearchCreateResponse>("/api/v1/searches", {
    method: "POST",
    body: JSON.stringify({ user_id: requireUserId(), ...body }),
  });
}

export async function getSearches(
  opts: { userId?: number; teamId?: string; memberUserId?: number } = {},
): Promise<SearchSummary[]> {
  const id = opts.userId ?? requireUserId();
  const params = new URLSearchParams({ user_id: String(id), limit: "50" });
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  return request<SearchSummary[]>(`/api/v1/searches?${params.toString()}`);
}

export async function getSearch(id: string): Promise<SearchSummary> {
  return request<SearchSummary>(`/api/v1/searches/${id}`);
}

export async function getSearchLeads(
  id: string,
  temp?: LeadTemp,
): Promise<Lead[]> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  if (temp) params.set("temp", temp);
  return request<Lead[]>(`/api/v1/searches/${id}/leads?${params.toString()}`);
}

export async function getAllLeads(
  opts: {
    userId?: number;
    teamId?: string;
    memberUserId?: number;
    leadStatus?: LeadStatus;
    temp?: LeadTemp;
    createdAfter?: Date | string;
    untouchedDays?: number;
    limit?: number;
  } = {},
): Promise<LeadListResponse> {
  const params = new URLSearchParams();
  params.set("user_id", String(opts.userId ?? requireUserId()));
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  if (opts.leadStatus) params.set("lead_status", opts.leadStatus);
  if (opts.temp) params.set("temp", opts.temp);
  if (opts.createdAfter) {
    const iso =
      opts.createdAfter instanceof Date
        ? opts.createdAfter.toISOString()
        : opts.createdAfter;
    params.set("created_after", iso);
  }
  if (opts.untouchedDays && opts.untouchedDays > 0)
    params.set("untouched_days", String(opts.untouchedDays));
  if (opts.limit) params.set("limit", String(opts.limit));
  return request<LeadListResponse>(`/api/v1/leads?${params.toString()}`);
}

export function leadsExportUrl(opts: {
  teamId?: string;
  memberUserId?: number;
} = {}): string {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  const base = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
  return `${base}/api/v1/leads/export.csv?${params.toString()}`;
}

export async function updateLead(id: string, patch: LeadUpdate): Promise<Lead> {
  return request<Lead>(`/api/v1/leads/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteLead(
  id: string,
  options: { forever?: boolean } = {},
): Promise<{ ok: boolean; forever: boolean }> {
  const qs = options.forever ? "?forever=true" : "";
  return request<{ ok: boolean; forever: boolean }>(
    `/api/v1/leads/${id}${qs}`,
    { method: "DELETE" },
  );
}

// ── User-defined tags ─────────────────────────────────────────────

export const TAG_COLORS = [
  "slate",
  "red",
  "orange",
  "yellow",
  "green",
  "teal",
  "blue",
  "violet",
  "pink",
] as const;
export type TagColor = (typeof TAG_COLORS)[number];

export const TAG_COLOR_HEX: Record<TagColor, string> = {
  slate: "#94A3B8",
  red: "#EF4444",
  orange: "#F97316",
  yellow: "#EAB308",
  green: "#22C55E",
  teal: "#14B8A6",
  blue: "#3B82F6",
  violet: "#8B5CF6",
  pink: "#EC4899",
};

export async function listTags(
  teamId?: string | null,
): Promise<{ items: LeadTag[] }> {
  const qs = teamId ? `?team_id=${encodeURIComponent(teamId)}` : "";
  return request<{ items: LeadTag[] }>(`/api/v1/tags${qs}`);
}

export async function createTag(args: {
  name: string;
  color?: TagColor | string;
  teamId?: string | null;
}): Promise<LeadTag> {
  return request<LeadTag>("/api/v1/tags", {
    method: "POST",
    body: JSON.stringify({
      name: args.name,
      color: args.color ?? null,
      team_id: args.teamId ?? null,
    }),
  });
}

export async function updateTag(
  id: string,
  patch: { name?: string; color?: string },
): Promise<LeadTag> {
  return request<LeadTag>(`/api/v1/tags/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteTag(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/tags/${id}`, { method: "DELETE" });
}

export async function assignLeadTags(
  leadId: string,
  tagIds: string[],
): Promise<{ items: LeadTag[] }> {
  return request<{ items: LeadTag[] }>(`/api/v1/leads/${leadId}/tags`, {
    method: "PUT",
    body: JSON.stringify({ tag_ids: tagIds }),
  });
}

export interface BulkDraftEmailItem {
  lead_id: string;
  subject: string | null;
  body: string | null;
  error: string | null;
}

export interface NotionIntegrationStatus {
  connected: boolean;
  token_preview: string | null;
  database_id: string | null;
  workspace_name: string | null;
  updated_at: string | null;
}

export async function getNotionStatus(): Promise<NotionIntegrationStatus> {
  return request<NotionIntegrationStatus>("/api/v1/integrations/notion");
}

export async function connectNotion(args: {
  token: string;
  databaseId: string;
}): Promise<NotionIntegrationStatus> {
  return request<NotionIntegrationStatus>("/api/v1/integrations/notion", {
    method: "PUT",
    body: JSON.stringify({
      token: args.token,
      database_id: args.databaseId,
    }),
  });
}

export async function disconnectNotion(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/v1/integrations/notion", {
    method: "DELETE",
  });
}

export interface NotionExportItem {
  lead_id: string;
  notion_url: string | null;
  error: string | null;
}

export async function exportLeadsToNotion(
  leadIds: string[],
): Promise<{
  items: NotionExportItem[];
  success_count: number;
  failure_count: number;
}> {
  return request<{
    items: NotionExportItem[];
    success_count: number;
    failure_count: number;
  }>("/api/v1/leads/export-to-notion", {
    method: "POST",
    body: JSON.stringify({ lead_ids: leadIds }),
  });
}

// ── Affiliate / referrals ─────────────────────────────────────────

export interface AffiliateCode {
  code: string;
  name: string | null;
  percent_share: number;
  active: boolean;
  created_at: string;
  referrals_count: number;
  paid_referrals_count: number;
}

export interface AffiliateOverview {
  codes: AffiliateCode[];
  total_referrals: number;
  total_paid_referrals: number;
}

export async function getAffiliateOverview(): Promise<AffiliateOverview> {
  return request<AffiliateOverview>("/api/v1/affiliate");
}

export async function createAffiliateCode(args: {
  code?: string | null;
  name?: string | null;
}): Promise<AffiliateCode> {
  return request<AffiliateCode>("/api/v1/affiliate/codes", {
    method: "POST",
    body: JSON.stringify({
      code: args.code ?? null,
      name: args.name ?? null,
    }),
  });
}

export async function updateAffiliateCode(
  code: string,
  patch: { name?: string | null; active?: boolean },
): Promise<AffiliateCode> {
  return request<AffiliateCode>(`/api/v1/affiliate/codes/${code}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteAffiliateCode(
  code: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/affiliate/codes/${code}`, {
    method: "DELETE",
  });
}

export async function bulkDraftEmails(args: {
  leadIds: string[];
  tone?: string;
  extraContext?: string | null;
}): Promise<{ items: BulkDraftEmailItem[] }> {
  return request<{ items: BulkDraftEmailItem[] }>(
    "/api/v1/leads/bulk-draft",
    {
      method: "POST",
      body: JSON.stringify({
        lead_ids: args.leadIds,
        tone: args.tone ?? "professional",
        extra_context: args.extraContext ?? null,
      }),
    },
  );
}

// CSV export URL is also same-origin via Next.js rewrites — drop the
// API_BASE prefix so the auth cookie attaches.
export function csvExportUrlSameOrigin(opts: {
  userId?: number;
  teamId?: string | null;
  memberUserId?: number | null;
} = {}): string {
  const params = new URLSearchParams();
  if (opts.userId !== undefined) params.set("user_id", String(opts.userId));
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined && opts.memberUserId !== null)
    params.set("member_user_id", String(opts.memberUserId));
  const qs = params.toString();
  return `/api/v1/leads/export.csv${qs ? "?" + qs : ""}`;
}

// ── CSV bulk import + decision-maker enrichment ────────────────────

export interface DecisionMaker {
  name: string;
  role: string | null;
  email: string | null;
  linkedin: string | null;
}

export async function enrichDecisionMakers(
  leadId: string,
): Promise<{ items: DecisionMaker[] }> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<{ items: DecisionMaker[] }>(
    `/api/v1/leads/${leadId}/enrich/decision-makers?${params.toString()}`,
    { method: "POST" },
  );
}

export interface CsvImportRow {
  name: string;
  website?: string | null;
  region?: string | null;
  phone?: string | null;
  category?: string | null;
  extras?: Record<string, string>;
}

export async function importLeadsCsv(input: {
  rows: CsvImportRow[];
  label?: string;
  teamId?: string;
}): Promise<{ search_id: string; inserted: number; skipped: number }> {
  return request<{ search_id: string; inserted: number; skipped: number }>(
    `/api/v1/searches/import-csv`,
    {
      method: "POST",
      body: JSON.stringify({
        user_id: requireUserId(),
        team_id: input.teamId ?? null,
        label: input.label ?? "CSV import",
        rows: input.rows,
      }),
    },
  );
}

export type EmailTone = "professional" | "casual" | "bold";

export interface LeadEmailDraft {
  subject: string;
  body: string;
  tone: EmailTone;
  notable_facts: string[];
  recent_signal: string | null;
}

export async function draftLeadEmail(
  leadId: string,
  opts: {
    tone?: EmailTone;
    extraContext?: string;
    deepResearch?: boolean;
  } = {},
): Promise<LeadEmailDraft> {
  return request<LeadEmailDraft>(`/api/v1/leads/${leadId}/draft-email`, {
    method: "POST",
    body: JSON.stringify({
      user_id: requireUserId(),
      tone: opts.tone ?? "professional",
      extra_context: opts.extraContext ?? null,
      deep_research: Boolean(opts.deepResearch),
    }),
  });
}

export interface LeadBulkUpdate {
  leadIds: string[];
  leadStatus?: LeadStatus;
  /** When provided (including ``null`` for clear), the caller's mark
   *  is set on every lead in the list. Omit to leave marks alone. */
  markColor?: LeadMarkColor | null;
}

export async function bulkUpdateLeads(
  patch: LeadBulkUpdate,
): Promise<{ updated: number }> {
  const body: Record<string, unknown> = {
    user_id: requireUserId(),
    lead_ids: patch.leadIds,
  };
  if (patch.leadStatus) body.lead_status = patch.leadStatus;
  if (patch.markColor !== undefined) {
    body.set_mark_color = true;
    body.mark_color = patch.markColor;
  }
  return request<{ updated: number }>("/api/v1/leads/bulk", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function setLeadMark(
  leadId: string,
  color: LeadMarkColor | null,
): Promise<Lead> {
  return request<Lead>(`/api/v1/leads/${leadId}/mark`, {
    method: "PUT",
    body: JSON.stringify({ user_id: requireUserId(), color }),
  });
}

export async function getStats(
  opts: { userId?: number; teamId?: string; memberUserId?: number } = {},
): Promise<DashboardStats> {
  const id = opts.userId ?? requireUserId();
  const params = new URLSearchParams({ user_id: String(id) });
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  return request<DashboardStats>(`/api/v1/stats?${params.toString()}`);
}

export async function getTeamMembersSummary(
  teamId: string,
  userId?: number,
): Promise<TeamMemberSummary[]> {
  const id = userId ?? requireUserId();
  return request<TeamMemberSummary[]>(
    `/api/v1/teams/${teamId}/members-summary?user_id=${id}`,
  );
}

export async function listMyTeams(userId?: number): Promise<TeamSummary[]> {
  const id = userId ?? requireUserId();
  return request<TeamSummary[]>(`/api/v1/teams?user_id=${id}`);
}

export async function getTeamDetail(
  teamId: string,
  userId?: number,
): Promise<TeamDetail> {
  const id = userId ?? requireUserId();
  return request<TeamDetail>(`/api/v1/teams/${teamId}?user_id=${id}`);
}

export async function createTeam(name: string): Promise<TeamDetail> {
  return request<TeamDetail>("/api/v1/teams", {
    method: "POST",
    body: JSON.stringify({ name, owner_user_id: requireUserId() }),
  });
}

export async function createInvite(
  teamId: string,
  opts: { role?: string; ttlSeconds?: number } = {},
): Promise<InviteResponse> {
  return request<InviteResponse>(`/api/v1/teams/${teamId}/invites`, {
    method: "POST",
    body: JSON.stringify({
      by_user_id: requireUserId(),
      role: opts.role ?? "member",
      ttl_seconds: opts.ttlSeconds ?? 600,
    }),
  });
}

export async function previewInvite(token: string): Promise<InvitePreview> {
  return request<InvitePreview>(`/api/v1/teams/invites/${token}`);
}

export async function acceptInvite(
  token: string,
  userId?: number,
): Promise<TeamDetail> {
  const id = userId ?? requireUserId();
  return request<TeamDetail>(`/api/v1/teams/invites/${token}/accept`, {
    method: "POST",
    body: JSON.stringify({ user_id: id }),
  });
}

// ── Utilities ───────────────────────────────────────────────────────

export function tempOf(score: number | null): LeadTemp {
  if (score === null || score === undefined) return "cold";
  if (score >= 75) return "hot";
  if (score >= 50) return "warm";
  return "cold";
}

export { ApiError };
