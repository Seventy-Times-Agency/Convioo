import { request } from "./_core";

/** Полная техническая сводка платформы (владелец и техник). Секретов нет. */
export interface TechInfo {
  generated_at: string;
  runtime: {
    commit: string;
    branch: string | null;
    environment: string | null;
    service: string | null;
    region: string | null;
    replica: string | null;
    private_domain: string | null;
    public_domain: string | null;
    python: string;
    platform: string;
    started_at: string;
    hosting: string;
    db_ok: boolean;
    db_dialect: string;
    db_revision: string | null;
    redis: boolean | null;
    queue_depth: number | null;
  };
  network: {
    app_url: string;
    api_via_app: string;
    api_direct: string;
    api_host_ips: string[];
    app_host_ips: string[];
    egress_ip: string | null;
    your_ip: string | null;
    cors_origins: string[];
    docs: { swagger: string; openapi: string; health: string; metrics: string };
  };
  auth: {
    api_key_header: string;
    api_key_where: string;
    session_cookie: string;
    csrf: string;
    roles: string[];
  };
  inbound: { name: string; method: string; url: string | null; auth: string }[];
  outbound_webhooks: {
    events: string[];
    manage: string;
    signature: string;
    signature_timestamped: string;
    timeout_s: number;
    disable_after_failures: number;
    yours: { id: string; url: string; events: string[]; active: boolean }[];
  };
  integrations: { key: string; name: string; purpose: string; configured: boolean; env: string[] }[];
  flags: Record<string, string | number | boolean | null>;
  jobs: { name: string; schedule: string; purpose: string }[];
  limits: Record<string, unknown> & { rate_limits: Record<string, string> };
  team: {
    id: string;
    name: string | null;
    your_user_id: number;
    members: { user_id: number; name: string | null; email: string | null; role: string; squad_id: string | null }[];
    funnels: { id: string; name: string; status: string }[];
    lead_statuses: { key: string; label: string; terminal: boolean }[];
  };
  api: { group: string; method: string; path: string; summary: string }[];
}

export async function getTechInfo(teamId: string): Promise<TechInfo> {
  return request<TechInfo>(`/api/v1/teams/${teamId}/tech-info`);
}
