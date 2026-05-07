import { request } from "./_core";

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
  onboarding_tour_completed: boolean;
  email: string | null;
  email_verified: boolean;
  recovery_email_masked: string | null;
  queries_used: number;
  queries_limit: number;
  calendly_url: string | null;
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
  calendly_url?: string | null;
}

export interface AuditLogEntry {
  id: string;
  action: string;
  ip: string | null;
  user_agent: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface NotificationPrefs {
  daily_digest_enabled: boolean;
  email_reply_tracking_enabled: boolean;
  email_reply_last_checked_at: string | null;
}

export type AssistantMemoryKind = "summary" | "fact";

export interface AssistantMemoryItem {
  id: string;
  kind: AssistantMemoryKind;
  content: string;
  team_id: string | null;
  created_at: string;
}

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

export async function getMyProfile(_userId?: number): Promise<UserProfile> {
  return request<UserProfile>("/api/v1/users/me");
}

export async function updateMyProfile(
  patch: UserProfileUpdate,
  _userId?: number,
): Promise<UserProfile> {
  return request<UserProfile>("/api/v1/users/me", {
    method: "PATCH",
    body: JSON.stringify(patch),
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

export async function listAuditLog(
  _userId?: number,
): Promise<{ items: AuditLogEntry[] }> {
  return request<{ items: AuditLogEntry[] }>(
    "/api/v1/users/me/audit-log",
  );
}

export function gdprExportUrl(_userId?: number): string {
  return "/api/v1/users/me/export";
}

export function sessionXlsxUrl(sessionId: string): string {
  return `/api/v1/searches/${sessionId}/export.xlsx`;
}

export async function deleteAccount(args: {
  confirmEmail: string;
  password?: string;
  userId?: number;
}): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>("/api/v1/users/me", {
    method: "DELETE",
    body: JSON.stringify({
      confirm_email: args.confirmEmail,
      password: args.password,
    }),
  });
}

export async function listAssistantMemory(opts: { teamId?: string } = {}): Promise<{
  items: AssistantMemoryItem[];
}> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  const qs = params.toString();
  return request<{ items: AssistantMemoryItem[] }>(
    `/api/v1/users/me/assistant-memory${qs ? `?${qs}` : ""}`,
  );
}

export async function clearAssistantMemory(opts: { teamId?: string } = {}): Promise<{
  deleted: number;
}> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  const qs = params.toString();
  return request<{ deleted: number }>(
    `/api/v1/users/me/assistant-memory${qs ? `?${qs}` : ""}`,
    { method: "DELETE" },
  );
}

export async function suggestNiches(): Promise<{ suggestions: string[] }> {
  return request<{ suggestions: string[] }>(
    "/api/v1/users/me/suggest-niches",
    { method: "POST" },
  );
}

export async function getNotificationPrefs(): Promise<NotificationPrefs> {
  return request<NotificationPrefs>("/api/v1/users/me/notifications");
}

export async function updateNotificationPrefs(patch: {
  dailyDigestEnabled?: boolean;
  emailReplyTrackingEnabled?: boolean;
}): Promise<NotificationPrefs> {
  return request<NotificationPrefs>("/api/v1/users/me/notifications", {
    method: "PATCH",
    body: JSON.stringify({
      ...(patch.dailyDigestEnabled !== undefined && {
        daily_digest_enabled: patch.dailyDigestEnabled,
      }),
      ...(patch.emailReplyTrackingEnabled !== undefined && {
        email_reply_tracking_enabled: patch.emailReplyTrackingEnabled,
      }),
    }),
  });
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
