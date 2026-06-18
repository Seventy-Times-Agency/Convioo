import { request } from "./_core";

/**
 * Wave 2 — Deliverability client.
 *
 * Two surfaces:
 *  - `getDeliverabilityStatus` powers the settings section (warmup
 *    progress + SPF/DMARC domain authentication).
 *  - `verifyLeadEmail` re-runs a single lead's email verification and
 *    returns the refreshed status so the badge can update in place.
 */

export type EmailStatus = "valid" | "risky" | "invalid" | "unknown";

export interface DeliverabilityDnsRecord {
  present: boolean;
  record: string | null;
}

export interface DeliverabilityDmarc {
  present: boolean;
  policy: string | null;
}

export interface DeliverabilityStatus {
  connected: boolean;
  provider: string | null;
  domain: string | null;
  warmup_day: number;
  daily_cap: number;
  sent_today: number;
  remaining: number;
  spf: DeliverabilityDnsRecord;
  dmarc: DeliverabilityDmarc;
}

export interface VerifyEmailResult {
  contact_email: string | null;
  email_status: string | null;
  email_checked_at: string | null;
}

export async function getDeliverabilityStatus(): Promise<DeliverabilityStatus> {
  return request<DeliverabilityStatus>("/api/v1/deliverability/status");
}

export async function verifyLeadEmail(id: string): Promise<VerifyEmailResult> {
  return request<VerifyEmailResult>(`/api/v1/leads/${id}/verify-email`, {
    method: "POST",
  });
}
