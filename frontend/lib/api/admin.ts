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
