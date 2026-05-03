/** Gmail OAuth integration — connect, send-as-user. */

import { request } from "./_core";

export interface GmailIntegrationStatus {
  connected: boolean;
  account_email: string | null;
  scope: string | null;
  expires_at: string | null;
}

export async function getGmailStatus(): Promise<GmailIntegrationStatus> {
  return request<GmailIntegrationStatus>("/api/v1/oauth/gmail");
}

export async function startGmailAuthorize(): Promise<{ url: string; state: string }> {
  return request<{ url: string; state: string }>(
    "/api/v1/oauth/gmail/authorize",
  );
}

export async function disconnectGmail(): Promise<void> {
  await request<{ ok: boolean }>("/api/v1/oauth/gmail", { method: "DELETE" });
}

export async function sendLeadEmail(args: {
  leadId: string;
  subject: string;
  body: string;
  to?: string;
  provider?: "gmail" | "outlook";
}): Promise<{ message_id: string; thread_id: string | null; sent_at: string }> {
  return request(`/api/v1/leads/${args.leadId}/send-email`, {
    method: "POST",
    body: JSON.stringify({
      subject: args.subject,
      body: args.body,
      to: args.to,
      provider: args.provider ?? "gmail",
    }),
  });
}
