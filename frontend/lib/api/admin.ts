/** Platform-wide admin / ops dashboard. */

import { request } from "./_core";

export interface AdminTopUser {
  user_id: number;
  name: string;
  email: string | null;
  plan: string;
  queries_used: number;
  is_admin: boolean;
}

export interface AdminOverview {
  users_total: number;
  users_paid: number;
  users_trialing: number;
  teams_total: number;
  searches_last_7d: number;
  searches_running: number;
  leads_last_7d: number;
  failed_searches_last_24h: number;
  top_users_by_searches: AdminTopUser[];
}

export async function getAdminOverview(): Promise<AdminOverview> {
  return request<AdminOverview>("/api/v1/admin/overview");
}

export interface SlowSearchEntry {
  search_id: string;
  niche: string;
  region: string;
  duration_seconds: number;
  leads_count: number;
  status: string;
  user_id: number | null;
  finished_at: string | null;
}

export interface AdminQuality {
  anthropic_calls_total: number;
  anthropic_calls_failed: number;
  anthropic_estimated_spend_usd: number;
  searches_total_24h: number;
  searches_failed_24h: number;
  searches_failure_rate_24h: number;
  queue_pending: number;
  queue_running: number;
  slowest_searches: SlowSearchEntry[];
}

export async function getAdminQuality(): Promise<AdminQuality> {
  return request<AdminQuality>("/api/v1/admin/quality");
}

export interface SourceHealthEntry {
  source: string;
  status: string;
  latency_ms: number | null;
  detail: string | null;
  http_status: number | null;
}

export async function getAdminSourcesHealth(): Promise<{
  sources: SourceHealthEntry[];
}> {
  return request<{ sources: SourceHealthEntry[] }>(
    "/api/v1/admin/sources/health",
  );
}
