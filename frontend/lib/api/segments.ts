/** Saved CRM segments / smart-views. */

import { request } from "./_core";

export interface LeadSegment {
  id: string;
  name: string;
  team_id: string | null;
  filter_json: Record<string, unknown>;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export async function listLeadSegments(): Promise<{ items: LeadSegment[] }> {
  return request<{ items: LeadSegment[] }>("/api/v1/segments");
}

export async function createLeadSegment(args: {
  name: string;
  filterJson: Record<string, unknown>;
  teamId?: string | null;
}): Promise<LeadSegment> {
  return request<LeadSegment>("/api/v1/segments", {
    method: "POST",
    body: JSON.stringify({
      name: args.name,
      filter_json: args.filterJson,
      team_id: args.teamId ?? null,
    }),
  });
}

export async function updateLeadSegment(
  id: string,
  args: {
    name?: string;
    filterJson?: Record<string, unknown>;
    sortOrder?: number;
  },
): Promise<LeadSegment> {
  const body: Record<string, unknown> = {};
  if (args.name !== undefined) body.name = args.name;
  if (args.filterJson !== undefined) body.filter_json = args.filterJson;
  if (args.sortOrder !== undefined) body.sort_order = args.sortOrder;
  return request<LeadSegment>(`/api/v1/segments/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteLeadSegment(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/api/v1/segments/${id}`, {
    method: "DELETE",
  });
}
