"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { LeadCard } from "@/components/app/LeadCard";
import { LeadDetailModal } from "@/components/app/LeadDetailModal";
import {
  type Lead,
  type LeadTemp,
  type SearchSummary,
  getSearch,
  getSearchLeads,
  sessionXlsxUrl,
  tempOf,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

type Filter = "all" | LeadTemp;

const POLL_INTERVAL_MS = 4000;

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const searchId = params.id;
  const { t } = useLocale();

  const [session, setSession] = useState<SearchSummary | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [active, setActive] = useState<Lead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const [s, ls] = await Promise.all([
          getSearch(searchId),
          getSearchLeads(searchId),
        ]);
        if (cancelledRef.current) return;
        setSession(s);
        setLeads(ls);
        if (s.status === "running" || s.status === "pending") {
          timer = setTimeout(tick, POLL_INTERVAL_MS);
        }
      } catch (e) {
        if (!cancelledRef.current) {
          setError(e instanceof Error ? e.message : String(e));
        }
      }
    };

    tick();

    return () => {
      cancelledRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [searchId]);

  const tempCounts = useMemo(() => {
    const counts: Record<LeadTemp, number> = { hot: 0, warm: 0, cold: 0 };
    for (const l of leads) counts[tempOf(l.score_ai)]++;
    return counts;
  }, [leads]);

  const filtered = useMemo(
    () =>
      filter === "all"
        ? leads
        : leads.filter((l) => tempOf(l.score_ai) === filter),
    [filter, leads],
  );

  const statusKey = (session?.status ?? "pending") as
    | "pending"
    | "running"
    | "done"
    | "failed";
  const isWorking = statusKey === "running" || statusKey === "pending";
  const enrichedCount = leads.filter((l) => l.score_ai !== null).length;

  return (
    <>
      <Topbar
        crumbs={[
          { label: t("search.crumb.workspace"), href: "/app" },
          { label: t("detail.crumb.sessions"), href: "/app/sessions" },
          { label: session?.niche ?? "…" },
        ]}
        right={
          <a
            className="btn btn-sm"
            href={sessionXlsxUrl(searchId)}
            target="_blank"
            rel="noopener noreferrer"
            aria-disabled={leads.length === 0}
            style={leads.length === 0 ? { pointerEvents: "none", opacity: 0.5 } : undefined}
          >
            <Icon name="download" size={14} /> {t("common.excel")}
          </a>
        }
      />
      <div className="page">
        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              color: "var(--cold)",
              borderColor: "var(--cold)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}

        {session && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: isWorking
                  ? "1fr"
                  : "1fr auto auto auto auto",
                gap: 16,
                marginBottom: 24,
                alignItems: "center",
              }}
            >
              <div>
                <div className="eyebrow" style={{ marginBottom: 6 }}>
                  <Icon
                    name="mapPin"
                    size={11}
                    style={{ verticalAlign: "-2px", marginRight: 4 }}
                  />
                  {session.region}
                </div>
                <div
                  style={{
                    fontSize: 38,
                    fontWeight: 700,
                    letterSpacing: "-0.025em",
                    lineHeight: 1.05,
                  }}
                >
                  {session.niche}
                </div>
                <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                  <span className="chip">
                    {isWorking && (
                      <span
                        className="status-dot live"
                        style={{ marginRight: 6 }}
                      />
                    )}
                    {t(`detail.status.${statusKey}` as TranslationKey)}
                  </span>
                  <span className="chip">
                    {session.source === "web"
                      ? t("detail.source.web")
                      : t("detail.source.telegram")}
                  </span>
                </div>
              </div>
              {!isWorking &&
                [
                  {
                    n: session.leads_count,
                    l: t("detail.stat.total"),
                    c: "var(--text)",
                  },
                  { n: tempCounts.hot, l: t("detail.stat.hot"), c: "var(--hot)" },
                  { n: tempCounts.warm, l: t("detail.stat.warm"), c: "#B45309" },
                  { n: tempCounts.cold, l: t("detail.stat.cold"), c: "var(--cold)" },
                ].map((s) => (
                  <div key={s.l} style={{ textAlign: "right", minWidth: 70 }}>
                    <div
                      style={{
                        fontSize: 28,
                        fontWeight: 700,
                        color: s.c,
                        fontFamily: "var(--font-mono)",
                        letterSpacing: "-0.02em",
                      }}
                    >
                      {s.n}
                    </div>
                    <div className="eyebrow" style={{ fontSize: 10 }}>{s.l}</div>
                  </div>
                ))}
            </div>

            {isWorking ? (
              <SessionLoader
                done={enrichedCount}
                total={leads.length}
                statusKey={statusKey}
              />
            ) : (
              <>
                {session.insights && (
                  <div
                    className="card"
                    style={{
                      padding: "20px 24px",
                      marginBottom: 20,
                      background:
                        "linear-gradient(135deg, var(--surface), color-mix(in srgb, var(--accent) 4%, var(--surface)))",
                      border:
                        "1px solid color-mix(in srgb, var(--accent) 20%, var(--border))",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                      <div
                        style={{
                          width: 36,
                          height: 36,
                          borderRadius: 10,
                          background: "var(--accent-soft)",
                          display: "grid",
                          placeItems: "center",
                          color: "var(--accent)",
                          flexShrink: 0,
                        }}
                      >
                        <Icon name="sparkles" size={18} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <div
                          className="eyebrow"
                          style={{ marginBottom: 4, color: "var(--accent)" }}
                        >
                          {t("detail.insights.eyebrow")}
                        </div>
                        <div
                          style={{
                            fontSize: 15,
                            lineHeight: 1.55,
                            color: "var(--text)",
                            maxWidth: 820,
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {session.insights}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 14,
                  }}
                >
                  <div className="seg">
                    {(["all", "hot", "warm", "cold"] as const).map((k) => {
                      const count = k === "all" ? leads.length : tempCounts[k];
                      return (
                        <button
                          key={k}
                          className={filter === k ? "active" : ""}
                          onClick={() => setFilter(k)}
                          type="button"
                        >
                          {k !== "all" && (
                            <span
                              className={"status-dot " + k}
                              style={{ marginRight: 6 }}
                            />
                          )}
                          {t(`detail.filter.${k}` as TranslationKey, { n: count })}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {leads.length === 0 && (
                  <div
                    className="card"
                    style={{
                      padding: 32,
                      textAlign: "center",
                      color: "var(--text-muted)",
                    }}
                  >
                    {t("detail.empty")}
                  </div>
                )}

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                    gap: 14,
                  }}
                >
                  {filtered.map((lead) => (
                    <LeadCard
                      key={lead.id}
                      lead={lead}
                      onClick={() => setActive(lead)}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {active && (
        <LeadDetailModal
          lead={active}
          onClose={() => setActive(null)}
          onUpdated={(updated) => {
            setLeads((prev) =>
              prev.map((l) => (l.id === updated.id ? updated : l)),
            );
          }}
          onDeleted={(leadId) => {
            setLeads((prev) => prev.filter((l) => l.id !== leadId));
          }}
        />
      )}
    </>
  );
}

function SessionLoader({
  done,
  total,
  statusKey,
}: {
  done: number;
  total: number;
  statusKey: "pending" | "running" | "done" | "failed";
}) {
  const { t } = useLocale();
  const pct = total > 0 ? Math.round((done / total) * 100) : 8;
  const phaseKey: TranslationKey =
    statusKey === "pending"
      ? "detail.loader.phase.pending"
      : total === 0
        ? "detail.loader.phase.discovering"
        : done === 0
          ? "detail.loader.phase.enriching"
          : "detail.loader.phase.scoring";

  return (
    <div
      className="card"
      style={{
        padding: "44px 36px",
        position: "relative",
        overflow: "hidden",
        textAlign: "center",
      }}
    >
      <div className="mesh-bg" style={{ opacity: 0.5 }} />
      <div className="hud-corner tl" />
      <div className="hud-corner tr" />
      <div className="hud-corner bl" />
      <div className="hud-corner br" />
      <div style={{ position: "relative", maxWidth: 460, margin: "0 auto" }}>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "50%",
            margin: "0 auto 18px",
            background: "linear-gradient(135deg, var(--accent), #EC4899)",
            display: "grid",
            placeItems: "center",
            color: "white",
          }}
        >
          <Icon name="sparkles" size={26} />
        </div>
        <div
          style={{
            fontSize: 24,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            margin: "0 0 8px",
          }}
        >
          {t("detail.loader.title")}
        </div>
        <div
          style={{
            fontSize: 14,
            color: "var(--text-muted)",
            lineHeight: 1.55,
            marginBottom: 24,
          }}
        >
          {t("detail.loader.subtitle")}
        </div>

        <div
          style={{
            height: 6,
            borderRadius: 3,
            background: "var(--surface-2)",
            overflow: "hidden",
            marginBottom: 12,
          }}
        >
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              background:
                "linear-gradient(90deg, var(--accent), #EC4899)",
              transition: "width .4s",
            }}
          />
        </div>
        <div
          className="eyebrow"
          style={{ fontSize: 11, color: "var(--text-muted)" }}
        >
          {t(phaseKey)}
          {total > 0 && ` · ${done}/${total}`}
        </div>
      </div>
    </div>
  );
}
