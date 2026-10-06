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

/* ── аналитика отдела продаж ──────────────────────────────────────── */

export type SalesPeriod = "week" | "month" | "quarter";

export interface SalesKpi {
  goals: number;
  goals_prev: number;
  goals_plan: number | null;
  dials: number;
  dials_prev: number;
  dials_plan: number | null;
  talks: number;
  reach_rate: number | null;
  quality_avg: number | null;
  quality_n: number;
  talk_avg_sec: number | null;
  money_in_work: number;
  money_closed: number;
  closed_count: number;
  days_to_first_call: number | null;
  overdue_callbacks: number;
  cooling_leads: number;
}

export interface SalesInsight {
  kind: "up" | "warn" | "bad" | "info";
  text: string;
}

export interface SalesDayPoint {
  date: string;
  dials: number;
  talks: number;
  goals: number;
}

export interface SalesFunnelStep {
  key: "found" | "in_work" | "dials" | "talks" | "goals" | "deals";
  count: number;
  rate: number | null;
}

export interface SalesBucket {
  key: string;
  count: number;
  share: number;
}

export interface SalesHeatCell {
  weekday: number;
  hour: number;
  dials: number;
  talks: number;
}

export interface SalesTempRow {
  temp: "hot" | "warm" | "cold";
  talks: number;
  goals: number;
  rate: number | null;
}

export interface SalesNicheRow {
  niche: string;
  talks: number;
  goals: number;
  rate: number | null;
}

export interface SalesMemberRow {
  user_id: number;
  name: string;
  role: string;
  avatar_url: string | null;
  dials: number;
  dials_plan: number | null;
  talks: number;
  reach_rate: number | null;
  goals: number;
  goals_plan: number | null;
  quality_avg: number | null;
  talk_avg_sec: number | null;
  overdue: number;
  hot_leads: number;
}

export interface SalesAnalytics {
  period: SalesPeriod;
  period_from: string;
  period_to: string;
  kpi: SalesKpi;
  insights: SalesInsight[];
  by_day: SalesDayPoint[];
  funnel: SalesFunnelStep[];
  outcomes: SalesBucket[];
  objections: SalesBucket[];
  heatmap: SalesHeatCell[];
  /** "weekday:hour:percent" или null. */
  best_window: string | null;
  emails: { sent: number; replied: number; hot: number };
  by_temp: SalesTempRow[];
  by_niche: SalesNicheRow[];
  members: SalesMemberRow[];
}

export async function getSalesAnalytics(
  teamId: string,
  period: SalesPeriod,
  squadId?: string | null,
): Promise<SalesAnalytics> {
  const params = new URLSearchParams({ period });
  if (squadId) params.set("squad_id", squadId);
  return request<SalesAnalytics>(
    `/api/v1/teams/${teamId}/sales-analytics?${params.toString()}`,
  );
}
