/** Unified Inbox (unibox) — threads, messages, reply, sync. */

import { request } from "./_core";

export interface InboxThreadSummary {
  thread_id: string;
  provider: string;
  subject: string | null;
  counterpart_email: string | null;
  lead_id: string | null;
  lead_name: string | null;
  last_message_at: string | null;
  snippet: string | null;
  unread_count: number;
  message_count: number;
}

export interface InboxThreadsResponse {
  connected: boolean;
  needs_reconnect: boolean;
  provider: string | null;
  threads: InboxThreadSummary[];
}

export interface InboxMessage {
  id: string;
  direction: "inbound" | "outbound";
  from_email: string | null;
  to_email: string | null;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  sent_at: string | null;
  is_read: boolean;
}

export interface InboxThreadDetail {
  thread_id: string;
  subject: string | null;
  lead_id: string | null;
  messages: InboxMessage[];
}

export interface InboxReplyResponse {
  ok: boolean;
  message_id: string | null;
}

export interface InboxSyncResponse {
  synced: number;
  needs_reconnect: boolean;
}

export async function getInboxThreads(
  opts: {
    unread?: boolean;
    leadId?: string;
    limit?: number;
    offset?: number;
  } = {},
  init: RequestInit = {},
): Promise<InboxThreadsResponse> {
  const params = new URLSearchParams();
  if (opts.unread !== undefined) params.set("unread", String(opts.unread));
  if (opts.leadId) params.set("lead_id", opts.leadId);
  if (opts.limit !== undefined) params.set("limit", String(opts.limit));
  if (opts.offset !== undefined) params.set("offset", String(opts.offset));
  const qs = params.toString();
  return request<InboxThreadsResponse>(
    `/api/v1/inbox/threads${qs ? `?${qs}` : ""}`,
    init,
  );
}

export async function getInboxThread(
  threadId: string,
  init: RequestInit = {},
): Promise<InboxThreadDetail> {
  return request<InboxThreadDetail>(
    `/api/v1/inbox/threads/${encodeURIComponent(threadId)}`,
    init,
  );
}

export async function replyInThread(
  threadId: string,
  body: string,
  subject?: string | null,
): Promise<InboxReplyResponse> {
  return request<InboxReplyResponse>(
    `/api/v1/inbox/threads/${encodeURIComponent(threadId)}/reply`,
    {
      method: "POST",
      body: JSON.stringify({ body, subject: subject ?? null }),
    },
  );
}

export async function syncInbox(): Promise<InboxSyncResponse> {
  return request<InboxSyncResponse>("/api/v1/inbox/sync", {
    method: "POST",
  });
}
