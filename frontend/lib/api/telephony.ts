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
