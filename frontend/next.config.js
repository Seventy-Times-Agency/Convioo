/** @type {import('next').NextConfig} */
const RAW_API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  // We proxy /api/* to the Railway backend so the browser sees a
  // single origin (convioo.com). That lets the auth cookie ride on
  // every API call as a first-party cookie — no cross-site session
  // shenanigans, no SameSite=None workarounds.

  async rewrites() {
    if (!RAW_API) return [];
    return [
      { source: "/api/:path*", destination: `${RAW_API}/api/:path*` },
      // /health and /metrics live at the API root (not under /api).
      // Mirror them through so admin tooling can hit one origin.
      { source: "/health", destination: `${RAW_API}/health` },
      { source: "/metrics", destination: `${RAW_API}/metrics` },
    ];
  },

  async redirects() {
    return [
      // The interactive prototype lives as static HTML in /public/prototype/.
      // Next.js doesn't auto-serve index.html for directory URLs, so map
      // /prototype and /prototype/ onto the actual file.
      { source: "/prototype", destination: "/prototype/index.html", permanent: false },
    ];
  },
};

// Wrap with Sentry's Next plugin only when configured. Skipping the
// wrap when the env vars are absent keeps dev / CI builds free of
// the source-map upload step (which would otherwise warn about
// missing auth tokens).
const SENTRY_AUTH_TOKEN = process.env.SENTRY_AUTH_TOKEN;
const SENTRY_ORG = process.env.SENTRY_ORG;
const SENTRY_PROJECT = process.env.SENTRY_PROJECT;

if (SENTRY_AUTH_TOKEN && SENTRY_ORG && SENTRY_PROJECT) {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { withSentryConfig } = require("@sentry/nextjs");
  module.exports = withSentryConfig(nextConfig, {
    org: SENTRY_ORG,
    project: SENTRY_PROJECT,
    authToken: SENTRY_AUTH_TOKEN,
    silent: true,
    widenClientFileUpload: true,
    hideSourceMaps: true,
    disableLogger: true,
  });
} else {
  module.exports = nextConfig;
}
