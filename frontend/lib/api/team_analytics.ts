/** Per-team analytics dashboard (owner-only). */

import { request } from "./_core";

export interface TeamAnalyticsStatusBucket {
  status: string;
  leads_count: number;
}

export interface TeamAnalyticsSourceBucket {
  source: string;
  leads_count: number;
}

export interface TeamAnalyticsMemberBucket {
  user_id: number;
  name: string;
  searches_total: number;
  leads_total: number;
  hot_leads: number;
  avg_score: number | null;
}

export interface TeamAnalyticsNicheBucket {
  niche: string;
  searches_total: number;
}

export interface TeamAnalyticsTimepoint {
  date: string;
  searches_total: number;
  leads_total: number;
}

export interface TeamAnalytics {
  team_id: string;
  period_from: string;
  period_to: string;
  searches_total: number;
  leads_total: number;
  avg_lead_score: number | null;
  avg_lead_cost_usd: number | null;
  status_breakdown: TeamAnalyticsStatusBucket[];
  top_source: TeamAnalyticsSourceBucket | null;
  top_member: TeamAnalyticsMemberBucket | null;
  top_niche: TeamAnalyticsNicheBucket | null;
  members: TeamAnalyticsMemberBucket[];
  sources: TeamAnalyticsSourceBucket[];
  niches: TeamAnalyticsNicheBucket[];
  timeseries: TeamAnalyticsTimepoint[];
}

export async function getTeamAnalytics(
  teamId: string,
  range?: { from?: string; to?: string },
): Promise<TeamAnalytics> {
  const params = new URLSearchParams();
  if (range?.from) params.set("from", range.from);
  if (range?.to) params.set("to", range.to);
  const qs = params.toString();
  return request<TeamAnalytics>(
    `/api/v1/teams/${teamId}/analytics${qs ? `?${qs}` : ""}`,
  );
}
