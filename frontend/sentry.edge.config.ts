// Sentry config for Vercel Edge runtime (middleware, edge route
// handlers). Same shape as the Node config; the SDK auto-selects
// based on the runtime so we keep three files just so the bundler
// tree-shakes correctly.

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "production",
    tracesSampleRate: 0.1,
  });
}
