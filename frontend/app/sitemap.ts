import type { MetadataRoute } from "next";

/**
 * Canonical marketing/site URL. Set NEXT_PUBLIC_SITE_URL in Vercel to the
 * production apex; falls back to convioo.com (the host used by the API,
 * support, and affiliate links).
 */
const SITE = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://convioo.com"
).replace(/\/$/, "");

const COMPETITORS = ["apollo", "clay", "lusha"];

export default function sitemap(): MetadataRoute.Sitemap {
  const staticPaths = [
    "/",
    "/pricing",
    "/changelog",
    "/help",
    "/developers",
    "/login",
    "/register",
    "/privacy",
    "/terms",
    "/cookies",
  ];

  const entries: MetadataRoute.Sitemap = staticPaths.map((path) => ({
    url: `${SITE}${path}`,
    changeFrequency: path === "/" ? "weekly" : "monthly",
    priority: path === "/" ? 1 : 0.7,
  }));

  for (const competitor of COMPETITORS) {
    entries.push({
      url: `${SITE}/vs/${competitor}`,
      changeFrequency: "monthly",
      priority: 0.8,
    });
  }

  return entries;
}
