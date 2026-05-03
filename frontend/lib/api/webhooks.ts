/**
 * Outbound webhook subscriptions — list, create, update, revoke, test.
 *
 * Backend reference: ``POST /api/v1/webhooks`` etc. The plaintext
 * ``secret`` is returned ONLY on creation; subsequent reads expose
 * a short ``secret_preview`` for UI recognition.
 */

import { request } from "./_core";

export const WEBHOOK_EVENTS = [
  "lead.created",
  "lead.status_changed",
  "search.finished",
] as const;

export type WebhookEvent = (typeof WEBHOOK_EVENTS)[number];

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
  /** Plaintext HMAC secret. Shown ONCE; copy now or rotate later. */
  secret: string;
}

export async function listWebhooks(): Promise<{ items: Webhook[] }> {
  return request<{ items: Webhook[] }>("/api/v1/webhooks");
}

export async function createWebhook(args: {
  targetUrl: string;
  eventTypes: string[];
  description?: string | null;
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
  const body: Record<string, unknown> = {};
  if (patch.targetUrl !== undefined) body.target_url = patch.targetUrl;
  if (patch.eventTypes !== undefined) body.event_types = patch.eventTypes;
  if (patch.description !== undefined) body.description = patch.description;
  if (patch.active !== undefined) body.active = patch.active;
  return request<Webhook>(`/api/v1/webhooks/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteWebhook(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/webhooks/${id}`, {
    method: "DELETE",
  });
}

export async function testWebhook(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/webhooks/${id}/test`, {
    method: "POST",
  });
}
