import { request } from "./_core";

/**
 * Recipient do-not-contact list. The backend consults it before every
 * outreach send so an unsubscribed / opted-out recipient is never
 * contacted again.
 */

export interface Suppression {
  email: string;
  reason: string | null;
  source: string | null;
  created_at: string;
}

export async function listSuppressions(): Promise<Suppression[]> {
  const res = await request<{ items: Suppression[] }>(
    "/api/v1/suppressions",
  );
  return res.items;
}

export async function addSuppression(
  email: string,
  reason?: string,
): Promise<Suppression> {
  return request<Suppression>("/api/v1/suppressions", {
    method: "POST",
    body: JSON.stringify({ email, reason: reason || null }),
  });
}

export async function removeSuppression(email: string): Promise<void> {
  await request(`/api/v1/suppressions/${encodeURIComponent(email)}`, {
    method: "DELETE",
  });
}
