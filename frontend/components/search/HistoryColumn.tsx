"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSearches, type SearchSummary } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/**
 * Правая колонка Добычи — Dobycha.dc.html: «Сейчас собирается» и
 * «История запусков». История отвечает на два вопроса менеджера:
 * «что уже искали» (чтобы не дублировать) и «что повторить».
 */
export function HistoryColumn({
  teamId,
  onRepeat,
}: {
  teamId: string | undefined;
  onRepeat: (niche: string, region: string) => void;
}) {
  const { t } = useLocale();
  const [rows, setRows] = useState<SearchSummary[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSearches(teamId ? { teamId } : {})
      .then((list) => {
        if (!cancelled) setRows(list.filter((r) => !r.archived_at));
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const running = (rows ?? []).filter(
    (r) => r.status === "running" || r.status === "pending",
  );
  const done = (rows ?? [])
    .filter((r) => r.status === "done" || r.status === "failed")
    .slice(0, 8);

  const when = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return t("dob.today");
    const yest = new Date(now);
    yest.setDate(now.getDate() - 1);
    if (d.toDateString() === yest.toDateString()) return t("dob.yesterday");
    return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
      {running.length > 0 && (
        <div className="card" style={{ padding: "16px 18px" }}>
          <div
            className="eyebrow"
            style={{ marginBottom: 10 }}
          >
            {t("dob.collecting")}
          </div>
          {running.map((r) => (
            <Link
              key={r.id}
              href={`/app/sessions/${r.id}`}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                textDecoration: "none",
                color: "inherit",
                padding: "6px 0",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                <span
                  style={{
                    fontWeight: 700,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {r.niche} · {r.region}
                </span>
                <span
                  style={{
                    color: "var(--text-dim)",
                    flexShrink: 0,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {r.leads_count > 0
                    ? t("dob.found", { n: r.leads_count })
                    : t("dob.starting")}
                </span>
              </div>
              <div
                style={{
                  height: 6,
                  borderRadius: 3,
                  background: "var(--surface-2)",
                  overflow: "hidden",
                }}
              >
                <div
                  className="dob-pulse"
                  style={{
                    width: "40%",
                    height: "100%",
                    background: "var(--accent)",
                  }}
                />
              </div>
            </Link>
          ))}
        </div>
      )}

      <div
        className="card"
        style={{ padding: 0, overflow: "hidden", flexGrow: 1 }}
      >
        <div
          style={{
            padding: "16px 16px 8px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
          }}
        >
          <span className="eyebrow">{t("dob.history")}</span>
          <Link
            href="/app/sessions"
            style={{ fontSize: 12, color: "var(--text-dim)" }}
          >
            {t("dob.allSessions")}
          </Link>
        </div>
        {rows === null ? (
          <div
            style={{
              padding: "10px 16px 16px",
              fontSize: 12.5,
              color: "var(--text-dim)",
            }}
          >
            …
          </div>
        ) : done.length === 0 ? (
          <div
            style={{
              padding: "10px 16px 16px",
              fontSize: 12.5,
              color: "var(--text-dim)",
              lineHeight: 1.5,
            }}
          >
            {t("dob.historyEmpty")}
          </div>
        ) : (
          done.map((r) => (
            <div
              key={r.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 16px",
                borderTop: "1px solid var(--border)",
                fontSize: 13,
              }}
            >
              <div style={{ minWidth: 0, flexGrow: 1 }}>
                <Link
                  href={`/app/sessions/${r.id}`}
                  style={{
                    display: "block",
                    fontWeight: 700,
                    color: "inherit",
                    textDecoration: "none",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {r.niche} · {r.region}
                </Link>
                <div
                  style={{
                    fontSize: 11.5,
                    color:
                      r.status === "failed"
                        ? "var(--cold)"
                        : "var(--text-dim)",
                    marginTop: 1,
                  }}
                >
                  {when(r.created_at)}
                  {" · "}
                  {r.status === "failed"
                    ? t("dob.failed")
                    : t("dob.doneLeads", { n: r.leads_count })}
                </div>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{ flexShrink: 0 }}
                onClick={() => onRepeat(r.niche, r.region)}
              >
                {t("dob.repeat")}
              </button>
            </div>
          ))
        )}
        <div
          style={{
            background: "var(--surface-2)",
            padding: "10px 16px",
            fontSize: 11.5,
            lineHeight: 1.5,
            color: "var(--text-dim)",
            textAlign: "center",
          }}
        >
          {t("dob.costNote")}
        </div>
      </div>
    </div>
  );
}
