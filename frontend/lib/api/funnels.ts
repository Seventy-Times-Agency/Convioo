import { request } from "./_core";

export interface FunnelStep {
  id?: string;
  order_index?: number;
  kind: "call" | "email";
  day_offset: number;
  auto: boolean;
  template_id?: string | null;
  note?: string | null;
}

export interface Funnel {
  id: string;
  team_id: string;
  name: string;
  status: "draft" | "active" | "archived";
  goal_name: string;
  goal_price: number | null;
  goal_action: "payment_calendar" | "invoice" | "booking" | "none";
  script: string | null;
  no_answer_attempts: number;
  no_answer_pause_days: number;
  leads_count: number;
  goals_reached: number;
  steps: FunnelStep[];
  created_at: string;
}

export interface FunnelDraft {
  name: string;
  goal_name: string;
  goal_price?: number | null;
  goal_action?: string;
  script?: string | null;
  status?: string;
  no_answer_attempts?: number;
  no_answer_pause_days?: number;
  steps?: FunnelStep[];
}

export async function listFunnels(teamId: string): Promise<Funnel[]> {
  return request<Funnel[]>(`/api/v1/teams/${teamId}/funnels`);
}

export async function createFunnel(
  teamId: string,
  draft: FunnelDraft,
): Promise<Funnel> {
  return request<Funnel>(`/api/v1/teams/${teamId}/funnels`, {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

export async function updateFunnel(
  funnelId: string,
  patch: Partial<FunnelDraft>,
): Promise<Funnel> {
  return request<Funnel>(`/api/v1/funnels/${funnelId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function duplicateFunnel(funnelId: string): Promise<Funnel> {
  return request<Funnel>(`/api/v1/funnels/${funnelId}/duplicate`, {
    method: "POST",
  });
}

export async function deleteFunnel(funnelId: string): Promise<void> {
  await request(`/api/v1/funnels/${funnelId}`, { method: "DELETE" });
}

export async function assignLeadsToFunnel(
  funnelId: string,
  leadIds: string[],
  ownerUserId?: number,
): Promise<{ assigned: number }> {
  return request<{ assigned: number }>(
    `/api/v1/funnels/${funnelId}/assign`,
    {
      method: "POST",
      body: JSON.stringify({
        lead_ids: leadIds,
        owner_user_id: ownerUserId ?? null,
      }),
    },
  );
}

export async function getLeadFunnel(leadId: string): Promise<Funnel | null> {
  return request<Funnel | null>(`/api/v1/leads/${leadId}/funnel`);
}
