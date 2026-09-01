import { request } from "./_core";

export interface TeamUsage {
  /** Баланс токенов — то, чем оперирует команда. Доллары ниже
   *  остаются внутренней себестоимостью. */
  token_balance: number;
  /** Скользящие 30 дней — то же окно, что у затрат. */
  tokens_spent_month: number;
  leads_month: number;
  emails_month: number;
  month_cost_usd: number;
  cap_usd: number | null;
  ratio: number | null;
  blocked: boolean;
  warning: boolean;
  cost_by_service: Record<string, number>;
  cost_per_lead_usd: number;
}

export interface SearchEstimate {
  leads: number;
  tokens: number;
  tokens_per_lead: number;
  tokens_breakdown: Record<string, number>;
  cost_usd: number;
  cost_per_lead_usd: number;
}

export async function getTeamUsage(teamId: string): Promise<TeamUsage> {
  return request<TeamUsage>(`/api/v1/teams/${teamId}/usage`);
}

export async function setTeamCostCap(
  teamId: string,
  capUsd: number | null,
): Promise<TeamUsage> {
  return request<TeamUsage>(`/api/v1/teams/${teamId}/cost-cap`, {
    method: "PATCH",
    body: JSON.stringify({ monthly_cost_cap_usd: capUsd }),
  });
}

export async function getSearchEstimate(
  leads: number,
  findDecisionMakers = false,
): Promise<SearchEstimate> {
  const p = new URLSearchParams({ leads: String(leads) });
  if (findDecisionMakers) p.set("find_decision_makers", "true");
  return request<SearchEstimate>(`/api/v1/searches/estimate?${p}`);
}
