import { request, requireUserId } from "./_core";

export type LeadTemp = "hot" | "warm" | "cold";
export type LeadStatus = string;
export const LEGACY_STATUS_KEYS = [
  "new",
  "contacted",
  "replied",
  "won",
  "archived",
] as const;

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
  deal_value: number | null;
  last_touched_at: string | null;
  mark_color: string | null;
  user_tags: LeadTag[];
  created_at: string;
  website_meta?: { emails?: string[] } | null;
  rating_snapshots?: Array<{ date: string; rating: number; reviews_count: number }> | null;
}

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

export interface LeadListResponse {
  leads: Lead[];
  total: number;
  sessions_by_id: Record<string, { niche: string; region: string }>;
}

export interface LeadUpdate {
  lead_status?: LeadStatus;
  owner_user_id?: number | null;
  notes?: string | null;
  deal_value?: number | null;
}

export interface LeadCustomField {
  id: string;
  lead_id: string;
  user_id: number;
  key: string;
  value: string | null;
  updated_at: string;
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

export interface LeadTask {
  id: string;
  lead_id: string;
  user_id: number;
  content: string;
  due_at: string | null;
  done_at: string | null;
  created_at: string;
}

export type EmailTone = "professional" | "casual" | "bold";

export interface LeadEmailDraft {
  subject: string;
  body: string;
  tone: EmailTone;
  notable_facts: string[];
  recent_signal: string | null;
}

export interface BulkDraftEmailItem {
  lead_id: string;
  subject: string | null;
  body: string | null;
  error: string | null;
}

export interface LeadBulkUpdate {
  leadIds: string[];
  leadStatus?: LeadStatus;
  markColor?: LeadMarkColor | null;
}

export interface DecisionMaker {
  name: string;
  role: string | null;
  email: string | null;
  linkedin: string | null;
}

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

export function tempOf(score: number | null): LeadTemp {
  if (score === null || score === undefined) return "cold";
  if (score >= 75) return "hot";
  if (score >= 50) return "warm";
  return "cold";
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

export async function reEnrichLead(id: string): Promise<Lead> {
  return request<Lead>(`/api/v1/leads/${id}/re-enrich`, { method: "POST" });
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

export async function listLeadActivity(
  leadId: string,
): Promise<{ items: LeadActivity[] }> {
  return request<{ items: LeadActivity[] }>(
    `/api/v1/leads/${leadId}/activity`,
  );
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
    `/api/v1/users/me/tasks${qs ? `?${qs}` : ""}`,
  );
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

export async function enrichDecisionMakers(
  leadId: string,
): Promise<{ items: DecisionMaker[] }> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<{ items: DecisionMaker[] }>(
    `/api/v1/leads/${leadId}/enrich/decision-makers?${params.toString()}`,
    { method: "POST" },
  );
}

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
