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

module.exports = nextConfig;
