"use client";

import Link from "next/link";
import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";
import type { SearchSummary } from "@/lib/api";

export function SessionRow({ session }: { session: SearchSummary }) {
  const { t } = useLocale();
  const isRunning = session.status === "running";
  const hot = session.hot_leads_count ?? 0;
  const rest = Math.max(0, session.leads_count - hot);

  return (
    <Link
      href={`/app/sessions/${session.id}`}
      className="card card-hover"
      style={{ display: "block", cursor: "pointer", padding: "16px 20px" }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto auto auto",
          gap: 20,
          alignItems: "center",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <span className={"status-dot " + (isRunning ? "live" : "hot")} />
            <div style={{ fontSize: 15, fontWeight: 600 }}>{session.niche}</div>
            <span className="chip" style={{ fontSize: 11 }}>
              <Icon name="mapPin" size={11} />
              {session.region}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {isRunning
              ? t("session.row.running", { status: session.status })
              : session.status === "failed"
                ? t("session.row.failed", { err: session.error ?? "error" })
                : t("session.row.summary", {
                    n: session.leads_count,
                    hot,
                  })}
          </div>
        </div>
        {!isRunning && session.status === "done" && (
          <>
            <div style={{ textAlign: "right" }}>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 18,
                  fontWeight: 700,
                  color: "var(--hot)",
                }}
              >
                {hot}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: "var(--text-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                }}
              >
                {t("session.row.hot")}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 18,
                  fontWeight: 700,
                  color: "#B45309",
                }}
              >
                {rest}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: "var(--text-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                }}
              >
                {t("session.row.rest")}
              </div>
            </div>
          </>
        )}
        <Icon name="chevronRight" size={16} style={{ color: "var(--text-dim)" }} />
      </div>
    </Link>
  );
}
