import { request } from "./_core";

export const WEBHOOK_EVENT_TYPES = [
  "lead.created",
  "lead.status_changed",
  "search.finished",
] as const;

export type WebhookEventType = (typeof WEBHOOK_EVENT_TYPES)[number];

export interface Webhook {
  id: string;
  target_url: string;
  event_types: string[];
  description: string | null;
  active: boolean;
  failure_count: number;
  secret_preview: string;
  last_delivery_at: string | null;
  last_delivery_status: number | null;
  last_failure_at: string | null;
  last_failure_message: string | null;
  created_at: string;
}

export interface WebhookCreated extends Webhook {
  secret: string;
}

export async function listWebhooks(): Promise<{ items: Webhook[] }> {
  return request<{ items: Webhook[] }>("/api/v1/webhooks");
}

export async function createWebhook(args: {
  targetUrl: string;
  eventTypes: string[];
  description?: string;
}): Promise<WebhookCreated> {
  return request<WebhookCreated>("/api/v1/webhooks", {
    method: "POST",
    body: JSON.stringify({
      target_url: args.targetUrl,
      event_types: args.eventTypes,
      description: args.description ?? null,
    }),
  });
}

export async function updateWebhook(
  id: string,
  patch: {
    targetUrl?: string;
    eventTypes?: string[];
    description?: string | null;
    active?: boolean;
  },
): Promise<Webhook> {
  return request<Webhook>(`/api/v1/webhooks/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...(patch.targetUrl !== undefined && { target_url: patch.targetUrl }),
      ...(patch.eventTypes !== undefined && { event_types: patch.eventTypes }),
      ...(patch.description !== undefined && { description: patch.description }),
      ...(patch.active !== undefined && { active: patch.active }),
    }),
  });
}

export async function deleteWebhook(id: string): Promise<void> {
  await request<unknown>(`/api/v1/webhooks/${id}`, { method: "DELETE" });
}

export async function testWebhook(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/webhooks/${id}/test`, {
    method: "POST",
  });
}
