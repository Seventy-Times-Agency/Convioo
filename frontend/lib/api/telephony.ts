import { request } from "./_core";

export interface TelephonyMember {
  user_id: number;
  name: string;
  role: string;
  phone_extension: string | null;
}

export interface TelephonyStatus {
  enabled: boolean;
  provider: string | null;
  transcription: boolean;
  my_extension: string | null;
  /** browser — звонок из вкладки (Telnyx), номер сотрудника не нужен;
   *  callback — провайдер сначала звонит сотруднику (Ringostat). */
  mode: "browser" | "callback";
  caller_number: string | null;
  webhook_url: string | null;
  webhook_params: string[];
  members: TelephonyMember[];
}

export interface CallAnalysis {
  summary?: string;
  next_step?: string | null;
  suggested_outcome?: string | null;
  callback_hint?: string | null;
  objections?: string[];
  sentiment?: string;
  quality_score?: number;
  quality_notes?: string;
}

export interface CallRecord {
  id: string;
  state: string;
  created_at: string;
  duration_sec: number | null;
  talk_sec: number | null;
  has_recording: boolean;
  transcript: { speaker: string; start: number; text: string }[] | null;
  analysis: CallAnalysis | null;
  error: string | null;
  user_name: string | null;
}

export async function getTelephonyStatus(
  teamId: string,
): Promise<TelephonyStatus> {
  return request<TelephonyStatus>(`/api/v1/teams/${teamId}/telephony`);
}

export async function setMemberPhone(
  teamId: string,
  userId: number,
  phone: string,
): Promise<void> {
  await request(`/api/v1/teams/${teamId}/members/${userId}/phone`, {
    method: "PATCH",
    body: JSON.stringify({ phone_extension: phone || null }),
  });
}

export interface StartCallResult {
  ok: boolean;
  call_id: string;
  mode: "browser" | "callback";
  /** Для режима браузера: кого набирать и с какого номера. */
  destination?: string;
  caller_number?: string | null;
}

/** Звонок через провайдера. callback — сначала зазвонит телефон
 *  сотрудника; browser — сервер завёл строку звонка, набирает вкладка. */
export async function startProviderCall(leadId: string): Promise<StartCallResult> {
  return request<StartCallResult>(`/api/v1/leads/${leadId}/call`, {
    method: "POST",
  });
}

export interface WebrtcToken {
  provider: string;
  token: string;
  caller_number: string | null;
  expires_in: number;
}

/** JWT для WebRTC-клиента; живёт сутки. */
export async function getWebrtcToken(teamId: string): Promise<WebrtcToken> {
  return request<WebrtcToken>("/api/v1/telephony/webrtc-token", {
    method: "POST",
    body: JSON.stringify({ team_id: teamId }),
  });
}

export async function getLeadCalls(leadId: string): Promise<CallRecord[]> {
  return request<CallRecord[]>(`/api/v1/leads/${leadId}/calls`);
}

/** Запись идёт через наш API по тому же адресу, что и остальные
 *  запросы (rewrite /api/* → Railway), чтобы cookie-сессия доходила;
 *  ссылка провайдера наружу не отдаётся. */
export function callRecordingUrl(callId: string): string {
  return `/api/v1/calls/${callId}/recording`;
}

/** Клиент против записи — выключить; передумал — включить обратно. */
export async function setCallConsent(
  callId: string,
  allowed: boolean,
): Promise<void> {
  await request(`/api/v1/calls/${callId}/consent`, {
    method: "POST",
    body: JSON.stringify({ allowed }),
  });
}

/* ── Архив звонков и общий разбор ─────────────────────────────────── */

export interface ArchivePerson {
  user_id: number;
  name: string;
  role: string;
  calls: number;
}

export interface ArchiveCall {
  id: string;
  created_at: string | null;
  lead_id: string | null;
  lead_name: string | null;
  to_number: string | null;
  direction: string;
  state: string;
  talk_sec: number | null;
  duration_sec: number | null;
  has_recording: boolean;
  has_transcript: boolean;
  transcript: { speaker: string; text: string }[] | null;
  summary: string | null;
  outcome: string | null;
  quality_score: number | null;
  objections: string[];
  quality_notes: string | null;
  error: string | null;
}

export interface ArchiveResult {
  calls: ArchiveCall[];
  stats: { total: number; talks: number; talk_min: number; avg_quality: number | null };
}

export interface CallReviewResult {
  summary?: string;
  score?: number;
  verdict?: "strong" | "ok" | "weak";
  mistakes?: { title: string; calls?: number[]; example?: string; fix?: string }[];
  objections?: { text: string; calls?: number[]; handled?: "well" | "partly" | "badly"; better_answer?: string }[];
  strengths?: string[];
  recommendations?: string[];
  per_call?: { n: number; score?: number; note?: string }[];
  call_map?: Record<string, string>;
}

export interface CallReview {
  id: string;
  status: "running" | "done" | "failed";
  created_at: string | null;
  finished_at: string | null;
  created_by: string | null;
  subject: string | null;
  subject_user_id: number | null;
  calls: number;
  call_ids: string[];
  focus: string | null;
  result?: CallReviewResult | null;
  error: string | null;
}

export async function getArchivePeople(teamId: string): Promise<ArchivePerson[]> {
  return request<ArchivePerson[]>(`/api/v1/teams/${teamId}/call-archive/people`);
}

export async function getArchiveCalls(
  teamId: string,
  args: { userId: number; dateFrom?: string; dateTo?: string; onlyTalks?: boolean },
): Promise<ArchiveResult> {
  const p = new URLSearchParams({ user_id: String(args.userId) });
  if (args.dateFrom) p.set("date_from", args.dateFrom);
  if (args.dateTo) p.set("date_to", args.dateTo);
  if (args.onlyTalks) p.set("only_talks", "true");
  return request<ArchiveResult>(`/api/v1/teams/${teamId}/call-archive?${p}`);
}

export async function createCallReview(teamId: string, callIds: string[], focus?: string): Promise<CallReview> {
  return request<CallReview>(`/api/v1/teams/${teamId}/call-reviews`, {
    method: "POST",
    body: JSON.stringify({ call_ids: callIds, focus: focus || null }),
  });
}

export async function listCallReviews(teamId: string, userId?: number): Promise<CallReview[]> {
  const q = userId != null ? `?user_id=${userId}` : "";
  return request<CallReview[]>(`/api/v1/teams/${teamId}/call-reviews${q}`);
}

export async function getCallReview(reviewId: string): Promise<CallReview> {
  return request<CallReview>(`/api/v1/call-reviews/${reviewId}`);
}
