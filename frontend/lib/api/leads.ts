import { API_BASE, request } from "./_core";
import type { EmailStatus } from "./deliverability";

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
  contact_email: string | null;
  email_status: EmailStatus | null;
  rating: number | null;
  reviews_count: number | null;
  score_ai: number | null;
  score_components?: Record<string, number>;
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
  archived_at: string | null;
  created_at: string;
  website_meta?: {
    emails?: string[];
    phones?: string[];
    pagespeed_mobile?: number;
    pagespeed_desktop?: number;
    has_ssl?: boolean;
    last_modified_year?: number;
    contact_person?: {
      name: string;
      title?: string;
      source?: string;
      source_label?: string;
    };
    [key: string]: unknown;
  } | null;
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
  | "created"
  | "email_sent"
  | "email_opened";

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
    teamId?: string;
    memberUserId?: number;
    leadStatus?: LeadStatus;
    temp?: LeadTemp;
    createdAfter?: Date | string;
    untouchedDays?: number;
    archived?: boolean;
    limit?: number;
  } = {},
): Promise<LeadListResponse> {
  const params = new URLSearchParams();
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
  if (opts.archived) params.set("archived", "true");
  if (opts.limit) params.set("limit", String(opts.limit));
  return request<LeadListResponse>(`/api/v1/leads?${params.toString()}`);
}

export function leadsExportUrl(opts: {
  teamId?: string;
  memberUserId?: number;
} = {}): string {
  // The export endpoint authenticates via the session cookie, so the
  // download must hit the same origin the rest of the API client uses
  // (API_BASE when configured, the Next.js /api rewrite otherwise).
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  const qs = params.toString();
  return `${API_BASE}/api/v1/leads/export.csv${qs ? "?" + qs : ""}`;
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

export async function archiveLead(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/leads/${id}/archive`, {
    method: "POST",
  });
}

export async function unarchiveLead(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/leads/${id}/unarchive`, {
    method: "POST",
  });
}

export async function listLeadCustomFields(
  leadId: string,
): Promise<{ items: LeadCustomField[] }> {
  return request<{ items: LeadCustomField[] }>(
    `/api/v1/leads/${leadId}/custom-fields`,
  );
}

export async function upsertLeadCustomField(
  leadId: string,
  key: string,
  value: string | null,
): Promise<LeadCustomField> {
  return request<LeadCustomField>(
    `/api/v1/leads/${leadId}/custom-fields`,
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
  await request<{ deleted: boolean }>(
    `/api/v1/leads/${leadId}/custom-fields/${encodeURIComponent(key)}`,
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
  return request<{ items: LeadTask[] }>(`/api/v1/leads/${leadId}/tasks`);
}

export async function createLeadTask(
  leadId: string,
  content: string,
  dueAt?: Date | null,
): Promise<LeadTask> {
  return request<LeadTask>(`/api/v1/leads/${leadId}/tasks`, {
    method: "POST",
    body: JSON.stringify({
      content,
      due_at: dueAt ? dueAt.toISOString() : null,
    }),
  });
}

export async function updateLeadTask(
  taskId: string,
  patch: { content?: string; due_at?: string | null; done?: boolean },
): Promise<LeadTask> {
  return request<LeadTask>(`/api/v1/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteLeadTask(taskId: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/v1/tasks/${taskId}`, {
    method: "DELETE",
  });
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

export type EmailDraftLanguage = "ru" | "uk" | "en";

export async function draftLeadEmail(
  leadId: string,
  opts: {
    tone?: EmailTone;
    extraContext?: string;
    deepResearch?: boolean;
    /** Per-email language override; omit for the interface language. */
    language?: EmailDraftLanguage;
  } = {},
): Promise<LeadEmailDraft> {
  return request<LeadEmailDraft>(`/api/v1/leads/${leadId}/draft-email`, {
    method: "POST",
    body: JSON.stringify({
      tone: opts.tone ?? "professional",
      extra_context: opts.extraContext ?? null,
      deep_research: Boolean(opts.deepResearch),
      language: opts.language ?? null,
    }),
  });
}

export async function bulkUpdateLeads(
  patch: LeadBulkUpdate,
): Promise<{ updated: number }> {
  const body: Record<string, unknown> = {
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
    body: JSON.stringify({ color }),
  });
}

export async function bulkDraftEmails(args: {
  leadIds: string[];
  tone?: string;
  extraContext?: string | null;
  /** Per-batch email language override; omit for the interface language. */
  language?: EmailDraftLanguage;
}): Promise<{ items: BulkDraftEmailItem[] }> {
  return request<{ items: BulkDraftEmailItem[] }>(
    "/api/v1/leads/bulk-draft",
    {
      method: "POST",
      body: JSON.stringify({
        lead_ids: args.leadIds,
        tone: args.tone ?? "professional",
        extra_context: args.extraContext ?? null,
        language: args.language ?? null,
      }),
    },
  );
}

export function csvExportUrlSameOrigin(opts: {
  teamId?: string | null;
  memberUserId?: number | null;
} = {}): string {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined && opts.memberUserId !== null)
    params.set("member_user_id", String(opts.memberUserId));
  const qs = params.toString();
  return `${API_BASE}/api/v1/leads/export.csv${qs ? "?" + qs : ""}`;
}

export async function enrichDecisionMakers(
  leadId: string,
): Promise<{ items: DecisionMaker[] }> {
  return request<{ items: DecisionMaker[] }>(
    `/api/v1/leads/${leadId}/enrich/decision-makers`,
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
