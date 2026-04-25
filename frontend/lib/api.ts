/**
 * Thin client for the Leadgen Railway API. Types mirror
 * src/leadgen/adapters/web_api/schemas.py — keep them in sync by
 * convention; once auth lands we should generate these from the
 * FastAPI OpenAPI schema.
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
  profession?: string;
}

export interface SearchCreateResponse {
  id: string;
  queued: boolean;
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
  created_at: string;
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
  business_size: string | null;
  profession: string | null;
  service_description: string | null;
  home_region: string | null;
  niches: string[] | null;
  language_code: string | null;
  onboarded: boolean;
}

export interface UserProfileUpdate {
  display_name?: string | null;
  age_range?: string | null;
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
  if (!API_BASE) {
    throw new ApiError(
      "NEXT_PUBLIC_API_URL is not set; frontend cannot reach the Leadgen backend.",
      0,
      null,
    );
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
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
  onboarded: boolean;
}

export async function registerUser(
  firstName: string,
  lastName: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ first_name: firstName, last_name: lastName }),
  });
}

export async function loginUser(
  firstName: string,
  lastName: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ first_name: firstName, last_name: lastName }),
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

export async function createSearch(
  body: SearchCreate & { team_id?: string },
): Promise<SearchCreateResponse> {
  return request<SearchCreateResponse>("/api/v1/searches", {
    method: "POST",
    body: JSON.stringify({ user_id: requireUserId(), ...body }),
  });
}

export async function getSearches(
  opts: { userId?: number; teamId?: string } = {},
): Promise<SearchSummary[]> {
  const id = opts.userId ?? requireUserId();
  const params = new URLSearchParams({ user_id: String(id), limit: "50" });
  if (opts.teamId) params.set("team_id", opts.teamId);
  return request<SearchSummary[]>(`/api/v1/searches?${params.toString()}`);
}

export async function getSearch(id: string): Promise<SearchSummary> {
  return request<SearchSummary>(`/api/v1/searches/${id}`);
}

export async function getSearchLeads(
  id: string,
  temp?: LeadTemp,
): Promise<Lead[]> {
  const q = temp ? `?temp=${temp}` : "";
  return request<Lead[]>(`/api/v1/searches/${id}/leads${q}`);
}

export async function getAllLeads(
  opts: {
    userId?: number;
    teamId?: string;
    leadStatus?: LeadStatus;
    limit?: number;
  } = {},
): Promise<LeadListResponse> {
  const params = new URLSearchParams();
  params.set("user_id", String(opts.userId ?? requireUserId()));
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.leadStatus) params.set("lead_status", opts.leadStatus);
  if (opts.limit) params.set("limit", String(opts.limit));
  return request<LeadListResponse>(`/api/v1/leads?${params.toString()}`);
}

export async function updateLead(id: string, patch: LeadUpdate): Promise<Lead> {
  return request<Lead>(`/api/v1/leads/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function getStats(
  opts: { userId?: number; teamId?: string } = {},
): Promise<DashboardStats> {
  const id = opts.userId ?? requireUserId();
  const params = new URLSearchParams({ user_id: String(id) });
  if (opts.teamId) params.set("team_id", opts.teamId);
  return request<DashboardStats>(`/api/v1/stats?${params.toString()}`);
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
