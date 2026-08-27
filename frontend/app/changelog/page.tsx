"use client";

import { PublicPageShell } from "@/components/PublicPageShell";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface Release {
  version: string;
  date: string;
  titleKey: TranslationKey;
  bullets: TranslationKey[];
}

const RELEASES: Release[] = [
  {
    version: "0.21",
    date: "2026-04-27",
    titleKey: "changelog.r21.title",
    bullets: [
      "changelog.r21.b1",
      "changelog.r21.b2",
      "changelog.r21.b3",
      "changelog.r21.b4",
    ],
  },
  {
    version: "0.20",
    date: "2026-04-27",
    titleKey: "changelog.r20.title",
    bullets: ["changelog.r20.b1", "changelog.r20.b2", "changelog.r20.b3"],
  },
  {
    version: "0.19",
    date: "2026-04-26",
    titleKey: "changelog.r19.title",
    bullets: ["changelog.r19.b1", "changelog.r19.b2"],
  },
  {
    version: "0.18",
    date: "2026-04-25",
    titleKey: "changelog.r18.title",
    bullets: ["changelog.r18.b1", "changelog.r18.b2", "changelog.r18.b3"],
  },
];

export default function ChangelogPage() {
  const { t } = useLocale();
  return (
    <PublicPageShell width={760}>
      <div style={{ marginBottom: 40 }}>
        <h1
          style={{
            fontSize: 36,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            margin: "0 0 10px",
          }}
        >
          {t("changelog.title")}
        </h1>
        <div style={{ fontSize: 15, color: "var(--text-muted)" }}>
          {t("changelog.subtitle")}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        {RELEASES.map((r) => (
          <article key={r.version} className="card" style={{ padding: 20 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 8,
              }}
            >
              <span
                className="chip"
                style={{
                  background: "var(--accent-soft)",
                  color: "var(--accent)",
                  fontWeight: 700,
                }}
              >
                v{r.version}
              </span>
              <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
                {r.date}
              </span>
            </div>
            <h2
              style={{
                fontSize: 18,
                fontWeight: 700,
                margin: "0 0 10px",
                letterSpacing: "-0.01em",
              }}
            >
              {t(r.titleKey)}
            </h2>
            <ul
              style={{
                margin: 0,
                paddingLeft: 22,
                fontSize: 14,
                color: "var(--text)",
                lineHeight: 1.7,
              }}
            >
              {r.bullets.map((b) => (
                <li key={b}>{t(b)}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </PublicPageShell>
  );
}
