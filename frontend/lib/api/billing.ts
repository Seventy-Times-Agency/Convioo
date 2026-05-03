/** Stripe billing — checkout, portal, subscription state. */

import { request } from "./_core";

export interface BillingSubscription {
  plan: "free" | "pro" | "agency";
  plan_until: string | null;
  trial_ends_at: string | null;
  trial_active: boolean;
  paid_active: boolean;
  has_stripe_customer: boolean;
  queries_used: number;
  queries_limit: number;
}

export async function getBillingSubscription(): Promise<BillingSubscription> {
  return request<BillingSubscription>("/api/v1/billing/subscription");
}

export async function startBillingCheckout(args: {
  plan: "pro" | "agency";
  successUrl: string;
  cancelUrl: string;
}): Promise<{ url: string; session_id: string }> {
  return request<{ url: string; session_id: string }>(
    "/api/v1/billing/checkout",
    {
      method: "POST",
      body: JSON.stringify({
        plan: args.plan,
        success_url: args.successUrl,
        cancel_url: args.cancelUrl,
      }),
    },
  );
}

export async function openBillingPortal(returnUrl: string): Promise<{ url: string }> {
  return request<{ url: string }>("/api/v1/billing/portal", {
    method: "POST",
    body: JSON.stringify({ return_url: returnUrl }),
  });
}
