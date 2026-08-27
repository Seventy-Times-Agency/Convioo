import { request } from "./_core";

export interface TeamUsage {
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
): Promise<SearchEstimate> {
  return request<SearchEstimate>(`/api/v1/searches/estimate?leads=${leads}`);
}
