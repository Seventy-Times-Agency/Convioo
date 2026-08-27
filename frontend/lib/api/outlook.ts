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

export async function startOutlookAuthorize(): Promise<{
  url: string;
  state: string;
}> {
  return request<{ url: string; state: string }>(
    "/api/v1/oauth/outlook/authorize"
  );
}

export async function disconnectOutlook(): Promise<void> {
  await request<{ ok: boolean }>("/api/v1/oauth/outlook", { method: "DELETE" });
}
