"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { SessionRow } from "@/components/app/SessionRow";
import {
  type DashboardStats,
  type Lead,
  type SearchSummary,
  getAllLeads,
  getSearches,
  getStats,
  tempOf,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";

export default function DashboardPage() {
  const { t } = useLocale();
  const [sessions, setSessions] = useState<SearchSummary[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [hotLeads, setHotLeads] = useState<Lead[]>([]);
  const [sessionTitles, setSessionTitles] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [s, st, ls] = await Promise.all([
          getSearches(),
          getStats(),
          getAllLeads({ limit: 50 }),
        ]);
        if (cancelled) return;
        setSessions(s);
        setStats(st);
        const byScore = [...ls.leads]
          .filter((l) => tempOf(l.score_ai) === "hot")
          .sort((a, b) => (b.score_ai ?? 0) - (a.score_ai ?? 0))
          .slice(0, 3);
        setHotLeads(byScore);
        const titles: Record<string, string> = {};
        for (const [id, meta] of Object.entries(ls.sessions_by_id)) {
          titles[id] = `${meta.niche} · ${meta.region}`;
        }
        setSessionTitles(titles);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const greeting =
    new Date().getHours() < 12
      ? t("dashboard.topbar.greetingMorning")
      : t("dashboard.topbar.greetingAfternoon");
  const running = sessions.filter((s) => s.status === "running");

  return (
    <>
      <Topbar
        title={greeting}
        subtitle={t("dashboard.topbar.subtitle")}
        right={
          <Link href="/app/search" className="btn">
            <Icon name="plus" size={15} />
            {t("common.newSearch")}
          </Link>
        }
      />
      <div className="page">
        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              marginBottom: 20,
              borderColor: "var(--cold)",
              color: "var(--cold)",
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            position: "relative",
            padding: "32px 28px",
            borderRadius: 16,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            overflow: "hidden",
            marginBottom: 24,
          }}
        >
          <div className="mesh-bg" style={{ opacity: 0.4 }} />
          <div
            style={{
              position: "relative",
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 20,
            }}
          >
            {[
              {
                n: stats?.sessions_total ?? 0,
                l: t("dashboard.stats.sessions"),
                sub: t("dashboard.stats.sessionsSub", { n: running.length }),
              },
              {
                n: stats?.leads_total ?? 0,
                l: t("dashboard.stats.leads"),
                sub: t("dashboard.stats.leadsSub"),
              },
              {
                n: stats?.hot_total ?? 0,
                l: t("dashboard.stats.hot"),
                sub: t("dashboard.stats.hotSub"),
                color: "var(--hot)",
              },
              {
                n: stats ? stats.warm_total + stats.cold_total : 0,
                l: t("dashboard.stats.rest"),
                sub: t("dashboard.stats.restSub"),
                color: "var(--accent)",
              },
            ].map((s) => (
              <div key={s.l}>
                <div
                  style={{
                    fontSize: 44,
                    fontWeight: 700,
                    letterSpacing: "-0.03em",
                    color: s.color || "var(--text)",
                  }}
                >
                  {s.n}
                </div>
                <div className="eyebrow" style={{ marginTop: 4 }}>{s.l}</div>
                <div
                  style={{
                    fontSize: 12.5,
                    color: "var(--text-muted)",
                    marginTop: 4,
                  }}
                >
                  {s.sub}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1.6fr 1fr",
            gap: 20,
            marginBottom: 24,
          }}
        >
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 14,
              }}
            >
              <div>
                <div className="eyebrow">{t("dashboard.recent.eyebrow")}</div>
                <div
                  style={{
                    fontSize: 22,
                    fontWeight: 600,
                    letterSpacing: "-0.01em",
                    marginTop: 4,
                  }}
                >
                  {t("dashboard.recent.title")}
                </div>
              </div>
              <Link
                href="/app/sessions"
                style={{ fontSize: 13, color: "var(--accent)" }}
              >
                {t("common.viewAll")}
              </Link>
            </div>
            {sessions.length === 0 && !error ? (
              <div
                className="card"
                style={{
                  padding: "32px 24px",
                  textAlign: "center",
                  color: "var(--text-muted)",
                }}
              >
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)" }}>
                  {t("dashboard.empty.title")}
                </div>
                <div style={{ fontSize: 13, marginTop: 6 }}>
                  {t("dashboard.empty.body")}
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {sessions.slice(0, 4).map((s) => (
                  <SessionRow key={s.id} session={s} />
                ))}
              </div>
            )}
          </div>

          <div>
            <div style={{ marginBottom: 14 }}>
              <div className="eyebrow">{t("dashboard.quick.eyebrow")}</div>
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 600,
                  letterSpacing: "-0.01em",
                  marginTop: 4,
                }}
              >
                {t("dashboard.quick.title")}
              </div>
            </div>
            <Link
              href="/app/search"
              className="card card-hover"
              style={{
                display: "block",
                cursor: "pointer",
                position: "relative",
                overflow: "hidden",
                background: "linear-gradient(135deg, var(--surface), var(--surface-2))",
              }}
            >
              <Icon name="sparkles" size={22} style={{ color: "var(--accent)" }} />
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 12, marginBottom: 6 }}>
                {t("dashboard.quick.launch.title")}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                {t("dashboard.quick.launch.body")}
              </div>
            </Link>
            <Link
              href="/app/leads"
              className="card card-hover"
              style={{ display: "block", cursor: "pointer", marginTop: 10 }}
            >
              <Icon name="list" size={22} style={{ color: "var(--text-muted)" }} />
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 12, marginBottom: 6 }}>
                {t("dashboard.quick.leads.title")}
              </div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
                {t("dashboard.quick.leads.body")}
              </div>
            </Link>
          </div>
        </div>

        {hotLeads.length > 0 && (
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 14,
              }}
            >
              <div>
                <div className="eyebrow">{t("dashboard.hot.eyebrow")}</div>
                <div
                  style={{
                    fontSize: 22,
                    fontWeight: 600,
                    letterSpacing: "-0.01em",
                    marginTop: 4,
                  }}
                >
                  {t("dashboard.hot.title")}
                </div>
              </div>
              <Link
                href="/app/leads"
                style={{ fontSize: 13, color: "var(--accent)" }}
              >
                {t("common.openCrm")}
              </Link>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: 14,
              }}
            >
              {hotLeads.map((lead) => (
                <Link
                  key={lead.id}
                  href={`/app/sessions/${lead.query_id}`}
                  className="card card-hover"
                  style={{ display: "block", cursor: "pointer" }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      justifyContent: "space-between",
                      marginBottom: 10,
                    }}
                  >
                    <div className="chip chip-hot">
                      <span className="status-dot hot" />
                      hot
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 22,
                        fontWeight: 700,
                        color: "var(--hot)",
                      }}
                    >
                      {Math.round(lead.score_ai ?? 0)}
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: 15,
                      fontWeight: 600,
                      letterSpacing: "-0.005em",
                      marginBottom: 4,
                    }}
                  >
                    {lead.name}
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-muted)",
                      marginBottom: 12,
                    }}
                  >
                    {sessionTitles[lead.query_id] ?? lead.address ?? ""}
                  </div>
                  {lead.summary && (
                    <div
                      style={{
                        fontSize: 13,
                        color: "var(--text-muted)",
                        lineHeight: 1.5,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {lead.summary}
                    </div>
                  )}
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
