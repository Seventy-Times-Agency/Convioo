import type { MetadataRoute } from "next";

const SITE = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://convioo.com"
).replace(/\/$/, "");

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // The authenticated workspace is private and has no SEO value.
      disallow: ["/app/", "/api/", "/r/", "/report/", "/join/"],
    },
    sitemap: `${SITE}/sitemap.xml`,
    host: SITE,
  };
}
