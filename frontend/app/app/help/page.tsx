"use client";

import { useMemo, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/**
 * Помощь — Help.dc.html. Поиск фильтрует частые вопросы на клиенте;
 * ИИ-ассистент по базе знаний помечен «скоро» — карточка стоит на
 * месте, чтобы привычка «спросить здесь» складывалась сразу.
 */

const FAQ: { q: TranslationKey; a: TranslationKey }[] = [
  { q: "hp.q1", a: "hp.a1" },
  { q: "hp.q2", a: "hp.a2" },
  { q: "hp.q3", a: "hp.a3" },
  { q: "hp.q4", a: "hp.a4" },
];

const CATS: { t: TranslationKey; b: TranslationKey }[] = [
  { t: "hp.cat1.t", b: "hp.cat1.b" },
  { t: "hp.cat2.t", b: "hp.cat2.b" },
  { t: "hp.cat3.t", b: "hp.cat3.b" },
];

export default function AppHelpPage() {
  const { t } = useLocale();
  const [query, setQuery] = useState("");

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return FAQ;
    return FAQ.filter(
      (item) =>
        t(item.q).toLowerCase().includes(q) ||
        t(item.a).toLowerCase().includes(q),
    );
  }, [query, t]);

  return (
    <>
      <Topbar title={t("nav.help")} />
      <div
        className="page"
        style={{ maxWidth: 860, display: "flex", flexDirection: "column", gap: 20 }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            alignItems: "center",
            textAlign: "center",
            marginTop: 12,
          }}
        >
          <div
            style={{
              fontSize: 26,
              fontWeight: 800,
              letterSpacing: "-0.02em",
            }}
          >
            {t("hp.heading")}
          </div>
          <div
            style={{
              width: "100%",
              maxWidth: 560,
              display: "flex",
              alignItems: "center",
              gap: 12,
              background: "var(--surface)",
              border: "1.5px solid var(--border)",
              borderRadius: 12,
              padding: "11px 16px",
            }}
          >
            <Icon
              name="search"
              size={17}
              style={{ color: "var(--text-dim)", flexShrink: 0 }}
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("hp.searchPh")}
              style={{
                border: "none",
                outline: "none",
                background: "transparent",
                width: "100%",
                fontSize: 14,
                color: "var(--text)",
              }}
            />
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: 12,
          }}
        >
          {CATS.map((c) => (
            <div
              key={c.t}
              className="card"
              style={{
                padding: "18px 20px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 800 }}>{t(c.t)}</div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                {t(c.b)}
              </div>
            </div>
          ))}
        </div>

        <div className="card" style={{ padding: "16px 22px" }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            {t("hp.faq")}
          </div>
          {shown.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-dim)" }}>
              {t("hp.noResults")}
            </div>
          ) : (
            shown.map((item, i) => (
              <details
                key={item.q}
                style={{
                  borderBottom:
                    i < shown.length - 1
                      ? "1px solid var(--border)"
                      : "none",
                  padding: "9px 0",
                }}
              >
                <summary
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 10,
                    fontSize: 14,
                    cursor: "pointer",
                    listStyle: "none",
                  }}
                >
                  <span>{t(item.q)}</span>
                  <span style={{ color: "var(--text-dim)" }}>›</span>
                </summary>
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-muted)",
                    lineHeight: 1.55,
                    padding: "8px 0 2px",
                    maxWidth: 640,
                  }}
                >
                  {t(item.a)}
                </div>
              </details>
            ))
          )}
        </div>

        <div
          className="card"
          style={{
            padding: "16px 22px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ fontSize: 14.5, fontWeight: 800 }}>
              {t("hp.ai.t")}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
              {t("hp.ai.b")}
            </div>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              border: "1.5px solid var(--border)",
              borderRadius: 10,
              padding: "9px 18px",
              fontSize: 13.5,
              fontWeight: 700,
              color: "var(--text-muted)",
              flexShrink: 0,
            }}
          >
            <span>{t("hp.ai.btn")}</span>
            <span
              style={{
                fontSize: 10,
                fontWeight: 800,
                color: "var(--warm)",
                border: "1px solid var(--warm)",
                borderRadius: 8,
                padding: "0 6px",
              }}
            >
              {t("hp.soon")}
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
