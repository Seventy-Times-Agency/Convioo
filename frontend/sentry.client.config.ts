// Sentry config for the browser bundle.
//
// When NEXT_PUBLIC_SENTRY_DSN is empty (default in dev / preview)
// the SDK never initialises and adds zero overhead. Production
// deploys set the DSN on Vercel as a project env var.

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "production",
    // Match backend's modest sample rate so the two projects stay in
    // sync at scale. 10% means we keep enough trace breadcrumbs to
    // diagnose issues without blowing the Sentry quota.
    tracesSampleRate: 0.1,
    // Replays are great UX for debugging but expensive — opt-in only.
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
  });
}
