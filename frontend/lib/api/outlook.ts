/** Outlook (Microsoft Graph) OAuth integration — connect, send-as-user. */

import { request } from "./_core";

export interface OutlookIntegrationStatus {
  connected: boolean;
  account_email: string | null;
  scope: string | null;
  expires_at: string | null;
}

export async function getOutlookStatus(): Promise<OutlookIntegrationStatus> {
  return request<OutlookIntegrationStatus>("/api/v1/oauth/outlook");
}

export async function startOutlookAuthorize(): Promise<{ url: string; state: string }> {
  return request<{ url: string; state: string }>(
    "/api/v1/oauth/outlook/authorize",
  );
}

export async function disconnectOutlook(): Promise<void> {
  await request<{ ok: boolean }>("/api/v1/oauth/outlook", { method: "DELETE" });
}

export async function getNotificationPrefs(): Promise<{ daily_digest: boolean }> {
  return request<{ daily_digest: boolean }>("/api/v1/users/me/notifications");
}

export async function setNotificationPrefs(prefs: {
  daily_digest?: boolean;
}): Promise<{ daily_digest: boolean }> {
  return request<{ daily_digest: boolean }>("/api/v1/users/me/notifications", {
    method: "PATCH",
    body: JSON.stringify(prefs),
  });
}
