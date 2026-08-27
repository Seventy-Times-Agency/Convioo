/** Custom CRM pipeline — per-team lead statuses. */

import { request } from "./_core";

export interface LeadStatusItem {
  id: string;
  key: string;
  label: string;
  color: string;
  order_index: number;
  is_terminal: boolean;
}

export async function listLeadStatuses(
  teamId: string,
): Promise<{ items: LeadStatusItem[] }> {
  return request<{ items: LeadStatusItem[] }>(
    `/api/v1/teams/${teamId}/statuses`,
  );
}

export async function createLeadStatus(
  teamId: string,
  body: {
    key: string;
    label: string;
    color?: string;
    is_terminal?: boolean;
  },
): Promise<LeadStatusItem> {
  return request<LeadStatusItem>(`/api/v1/teams/${teamId}/statuses`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateLeadStatus(
  teamId: string,
  statusId: string,
  patch: {
    label?: string;
    color?: string;
    order_index?: number;
    is_terminal?: boolean;
  },
): Promise<LeadStatusItem> {
  return request<LeadStatusItem>(
    `/api/v1/teams/${teamId}/statuses/${statusId}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export async function deleteLeadStatus(
  teamId: string,
  statusId: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/api/v1/teams/${teamId}/statuses/${statusId}`,
    { method: "DELETE" },
  );
}

export async function reorderLeadStatuses(
  teamId: string,
  orderedIds: string[],
): Promise<{ items: LeadStatusItem[] }> {
  return request<{ items: LeadStatusItem[] }>(
    `/api/v1/teams/${teamId}/statuses/reorder`,
    {
      method: "POST",
      body: JSON.stringify({ ordered_ids: orderedIds }),
    },
  );
}
