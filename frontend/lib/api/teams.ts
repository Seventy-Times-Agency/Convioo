import { request } from "./_core";

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
  /** Сколько лидов сейчас закреплено за участником. */
  leads_count?: number;
}

export interface TeamMemberSummary {
  user_id: number;
  name: string;
  role: string;
  sessions_total: number;
  leads_total: number;
  hot_total: number;
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
  /** Отправленные и ещё не принятые приглашения. */
  pending_invites?: number;
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

export interface WeeklyCheckin {
  summary: string;
  highlights: string[];
  leads_total: number;
  hot_total: number;
  new_this_week: number;
  untouched_14d: number;
  sessions_this_week: number;
}

export async function listMyTeams(): Promise<TeamSummary[]> {
  return request<TeamSummary[]>("/api/v1/teams");
}

export async function getTeamDetail(teamId: string): Promise<TeamDetail> {
  return request<TeamDetail>(`/api/v1/teams/${teamId}`);
}

export async function createTeam(name: string): Promise<TeamDetail> {
  return request<TeamDetail>("/api/v1/teams", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function updateTeam(
  teamId: string,
  patch: { name?: string; description?: string | null },
): Promise<TeamDetail> {
  return request<TeamDetail>(`/api/v1/teams/${teamId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
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
      body: JSON.stringify(patch),
    },
  );
}

export async function createInvite(
  teamId: string,
  opts: { role?: string; ttlSeconds?: number } = {},
): Promise<InviteResponse> {
  return request<InviteResponse>(`/api/v1/teams/${teamId}/invites`, {
    method: "POST",
    body: JSON.stringify({
      role: opts.role ?? "sales",
      ttl_seconds: opts.ttlSeconds ?? 600,
    }),
  });
}

export async function removeTeamMember(
  teamId: string,
  memberUserId: number,
  transferTo?: number,
): Promise<{ ok: boolean; transferred_leads: number }> {
  const qs = transferTo != null ? `?transfer_to=${transferTo}` : "";
  return request<{ ok: boolean; transferred_leads: number }>(
    `/api/v1/teams/${teamId}/members/${memberUserId}${qs}`,
    { method: "DELETE" },
  );
}

export async function transferOwnership(
  teamId: string,
  newOwnerUserId: number,
): Promise<TeamDetail> {
  return request<TeamDetail>(
    `/api/v1/teams/${teamId}/transfer-ownership`,
    {
      method: "POST",
      body: JSON.stringify({ new_owner_user_id: newOwnerUserId }),
    },
  );
}

export async function previewInvite(token: string): Promise<InvitePreview> {
  return request<InvitePreview>(`/api/v1/teams/invites/${token}`);
}

export async function acceptInvite(token: string): Promise<TeamDetail> {
  return request<TeamDetail>(`/api/v1/teams/invites/${token}/accept`, {
    method: "POST",
  });
}

export async function getTeamMembersSummary(
  teamId: string,
): Promise<TeamMemberSummary[]> {
  return request<TeamMemberSummary[]>(
    `/api/v1/teams/${teamId}/members-summary`,
  );
}

export async function getStats(
  opts: { teamId?: string; memberUserId?: number } = {},
): Promise<DashboardStats> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  const qs = params.toString();
  return request<DashboardStats>(`/api/v1/stats${qs ? `?${qs}` : ""}`);
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
    `/api/v1/users/me/weekly-checkin${qs ? `?${qs}` : ""}`,
  );
}

/** Воронка отдела по звонкам: наборы → дозвоны → цели. */
export interface CallFunnelRep {
  user_id: number;
  name: string;
  dials: number;
  connects: number;
  goals: number;
  connect_rate: number;
  goal_rate: number;
}

export interface CallFunnel {
  days: number;
  dials: number;
  connects: number;
  goals: number;
  connect_rate: number;
  goal_rate: number;
  by_day: { date: string; dials: number }[];
  by_rep: CallFunnelRep[];
}

export async function getTeamCallFunnel(
  teamId: string,
  days = 30,
): Promise<CallFunnel> {
  return request<CallFunnel>(
    `/api/v1/teams/${teamId}/analytics/calls?days=${days}`,
  );
}
