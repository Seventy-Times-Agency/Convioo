import { request } from "./_core";

/* ── Деньги и токены ─────────────────────────────────────────────── */

export interface TeamMoney {
  budget_usd: number | null;
  token_price_usd: number;
  allowance: number;
  balance: number;
  spent_month: number;
  stop_at_zero: boolean;
  month: string;
  by_day: { date: string; tokens: number }[];
  by_kind: { leads: number; decision_makers: number };
  by_person: { user_id: number | null; name: string; tokens: number }[];
}

export interface LedgerRow {
  at: string;
  kind: string;
  amount: number;
  balance_after: number;
  reason: string | null;
}

export async function getTeamMoney(teamId: string): Promise<TeamMoney> {
  return request<TeamMoney>(`/api/v1/teams/${teamId}/money`);
}

export async function updateTeamMoney(
  teamId: string,
  patch: { budget_usd?: number | null; stop_at_zero?: boolean; clear_budget?: boolean },
): Promise<TeamMoney> {
  return request<TeamMoney>(`/api/v1/teams/${teamId}/money`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function grantTeamTokens(teamId: string, tokens: number, reason?: string): Promise<TeamMoney> {
  return request<TeamMoney>(`/api/v1/teams/${teamId}/money/grant`, {
    method: "POST",
    body: JSON.stringify({ tokens, reason: reason || null }),
  });
}

export async function getTeamLedger(teamId: string): Promise<LedgerRow[]> {
  return request<LedgerRow[]>(`/api/v1/teams/${teamId}/money/ledger`);
}

/* ── Подключения ─────────────────────────────────────────────────── */

export interface MemberConnections {
  user_id: number;
  name: string;
  role: string;
  color: string;
  avatar_url: string | null;
  mail_provider: string | null;
  mail_address: string | null;
  telegram: boolean;
}

export async function getTeamConnections(
  teamId: string,
): Promise<{ telegram_bot: boolean; members: MemberConnections[] }> {
  return request(`/api/v1/teams/${teamId}/connections`);
}

export interface TelegramStatus {
  configured: boolean;
  bot_username: string | null;
  linked: boolean;
  linked_at: string | null;
}

export async function getTelegramStatus(): Promise<TelegramStatus> {
  return request<TelegramStatus>("/api/v1/telegram/status");
}

export async function createTelegramLink(): Promise<{ token: string; expires_in_seconds: number; deep_link: string | null }> {
  return request("/api/v1/telegram/link-token", { method: "POST" });
}

export async function unlinkTelegram(): Promise<void> {
  await request("/api/v1/telegram/link", { method: "DELETE" });
}
