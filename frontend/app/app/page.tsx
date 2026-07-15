"use client";

import { type ComponentProps, useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { SessionRow } from "@/components/app/SessionRow";
import {
  type DashboardStats,
  type Lead,
  type LeadTask,
  type SearchSummary,
  type UserProfile,
  type WeeklyCheckin,
  getAllLeads,
  getMyProfile,
  getSearches,
  getStats,
  getWeeklyCheckin,
  listMyTasks,
  tempOf,
  updateLeadTask,
} from "@/lib/api";
import { HenryAvatar } from "@/components/HenryAvatar";
import {
  activeMemberUserId,
  activeTeamId,
  subscribeWorkspace,
} from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { useIsMobile } from "@/lib/hooks/useMediaQuery";

// Curated first-run example searches. The {niche, region} values are the
// canonical English strings actually sent to the search API (the backend
// GooglePlacesCollector defaults to English regardless of UI locale);
// the user-visible labels come from i18n. EU / UK / US only — no Russian
// market (hard product rule).
const QUICKSTART_EXAMPLES: {
  niche: string;
  region: string;
  labelKey: TranslationKey;
}[] = [
  {
    niche: "Roofing companies",
    region: "New York",
    labelKey: "onboarding.quickstart.roofing",
  },
  {
    niche: "Dentists",
    region: "London",
    labelKey: "onboarding.quickstart.dentists",
  },
  {
    niche: "Marketing agencies",
    region: "Berlin",
    labelKey: "onboarding.quickstart.agencies",
  },
];

export default function DashboardPage() {
  const { t } = useLocale();
  const isMobile = useIsMobile();
  const [sessions, setSessions] = useState<SearchSummary[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [hotLeads, setHotLeads] = useState<Lead[]>([]);
  const [sessionTitles, setSessionTitles] = useState<Record<string, string>>({});
  const [workspaceTick, setWorkspaceTick] = useState(0);

  useEffect(
    () => subscribeWorkspace(() => setWorkspaceTick((n) => n + 1)),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const teamId = activeTeamId();
        const memberUserId = activeMemberUserId();
        const [s, st, ls] = await Promise.all([
          getSearches({ teamId, memberUserId }),
          getStats({ teamId, memberUserId }),
          getAllLeads({ limit: 50, teamId, memberUserId }),
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
        if (!cancelled) showError(e instanceof Error ? e.message : String(e));
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceTick]);

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
        {/* KPI tiles — compact glass tiles with a soft corner glow. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)",
            gap: 14,
            marginBottom: 22,
          }}
        >
          <Tile
            label={t("dashboard.stats.leads")}
            value={stats?.leads_total ?? 0}
            sub={t("dashboard.stats.leadsSub")}
            glow="rgba(139,92,246,.30)"
          />
          <Tile
            label={t("dashboard.stats.hot")}
            value={stats?.hot_total ?? 0}
            sub={t("dashboard.stats.hotSub")}
            valueColor="var(--hot)"
            glow="rgba(34,211,238,.26)"
          />
          <Tile
            label={t("dashboard.stats.sessions")}
            value={stats?.sessions_total ?? 0}
            sub={t("dashboard.stats.sessionsSub", { n: running.length })}
            glow="rgba(244,114,182,.26)"
          />
          <Tile
            label={t("dashboard.stats.rest")}
            value={stats ? stats.warm_total + stats.cold_total : 0}
            sub={t("dashboard.stats.restSub")}
            glow="rgba(139,92,246,.30)"
          />
        </div>

        {/* Work feed (left) + actionable rail (right). */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "1.6fr 1fr",
            gap: 20,
            alignItems: "start",
            marginBottom: 24,
          }}
        >
          {/* LEFT — continue where you left off, or a first-run quickstart. */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {sessions.length === 0 ? (
              <div className="card">
                <PanelHead
                  eyebrow={t("onboarding.quickstart.eyebrow")}
                  title={t("onboarding.quickstart.title")}
                />
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr" : "repeat(3, 1fr)",
                    gap: 12,
                  }}
                >
                  {QUICKSTART_EXAMPLES.map((ex) => (
                    <Link
                      key={ex.labelKey}
                      href={`/app/search?niche=${encodeURIComponent(
                        ex.niche,
                      )}&region=${encodeURIComponent(ex.region)}`}
                      className="card card-hover"
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        cursor: "pointer",
                        padding: 18,
                      }}
                    >
                      <Icon
                        name="sparkles"
                        size={18}
                        style={{ color: "var(--accent)" }}
                      />
                      <div
                        style={{
                          fontSize: 14.5,
                          fontWeight: 600,
                          marginTop: 10,
                          marginBottom: 10,
                          letterSpacing: "-0.005em",
                        }}
                      >
                        {t(ex.labelKey)}
                      </div>
                      <div
                        className="gradient-text"
                        style={{
                          marginTop: "auto",
                          fontSize: 12.5,
                          fontWeight: 700,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        {t("onboarding.quickstart.action")}
                        <Icon name="chevronRight" size={13} />
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            ) : (
              <div className="card">
                <PanelHead
                  title={t("dashboard.recent.title")}
                  href="/app/sessions"
                  action={t("common.viewAll")}
                />
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {sessions.slice(0, 5).map((s) => (
                    <SessionRow key={s.id} session={s} />
                  ))}
                </div>
              </div>
            )}

            {hotLeads.length > 0 && (
              <div className="card">
                <PanelHead
                  title={t("dashboard.hot.title")}
                  href="/app/leads"
                  action={t("common.openCrm")}
                />
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr" : "repeat(3, 1fr)",
                    gap: 12,
                  }}
                >
                  {hotLeads.map((lead) => (
                    <Link
                      key={lead.id}
                      href={`/app/sessions/${lead.query_id}`}
                      className="card card-hover"
                      style={{ display: "block", cursor: "pointer", padding: 16 }}
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
                            fontSize: 20,
                            fontWeight: 700,
                            color: "var(--hot)",
                          }}
                        >
                          {Math.round(lead.score_ai ?? 0)}
                        </div>
                      </div>
                      <div
                        style={{
                          fontSize: 14.5,
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
                        }}
                      >
                        {sessionTitles[lead.query_id] ?? lead.address ?? ""}
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* RIGHT — everything the user should act on, one column. */}
          <div>
            <QuotaWidget tick={workspaceTick} />
            <TodayTasksWidget tick={workspaceTick} />
            <HenryWeeklyCheckinCard tick={workspaceTick} />
            <div className="card" style={{ padding: 8 }}>
              <QuickLink
                href="/app/search"
                icon="sparkles"
                title={t("dashboard.quick.launch.title")}
                accent
              />
              <QuickLink
                href="/app/leads"
                icon="list"
                title={t("dashboard.quick.leads.title")}
              />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

/* A compact metric tile: glass surface + a single static corner glow. */
function Tile({
  label,
  value,
  sub,
  glow,
  valueColor,
}: {
  label: string;
  value: number;
  sub: string;
  glow: string;
  valueColor?: string;
}) {
  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: 16,
        padding: "18px 18px 16px",
        background: "var(--glass)",
        border: "1px solid var(--glass-bd)",
        backdropFilter: "blur(14px)",
        WebkitBackdropFilter: "blur(14px)",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: -34,
          right: -34,
          width: 110,
          height: 110,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${glow}, transparent 70%)`,
          pointerEvents: "none",
        }}
      />
      <div
        className="eyebrow"
        style={{ position: "relative", marginBottom: 10 }}
      >
        {label}
      </div>
      <div
        style={{
          position: "relative",
          fontSize: 30,
          fontWeight: 800,
          letterSpacing: "-0.02em",
          color: valueColor || "var(--text)",
        }}
      >
        {value}
      </div>
      <div
        style={{
          position: "relative",
          fontSize: 12,
          marginTop: 4,
          color: "var(--text-muted)",
        }}
      >
        {sub}
      </div>
    </div>
  );
}

/* Panel header: optional eyebrow + title on the left, a "see all" link right. */
function PanelHead({
  eyebrow,
  title,
  href,
  action,
}: {
  eyebrow?: string;
  title: string;
  href?: string;
  action?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 14,
        gap: 12,
      }}
    >
      <div>
        {eyebrow ? (
          <div className="eyebrow" style={{ marginBottom: 3 }}>
            {eyebrow}
          </div>
        ) : null}
        <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "-0.01em" }}>
          {title}
        </div>
      </div>
      {href && action ? (
        <Link href={href} className="gradient-text" style={{ fontSize: 12.5, fontWeight: 700 }}>
          {action}
        </Link>
      ) : null}
    </div>
  );
}

/* Slim navigation row used in the right rail. */
function QuickLink({
  href,
  icon,
  title,
  accent,
}: {
  href: string;
  icon: ComponentProps<typeof Icon>["name"];
  title: string;
  accent?: boolean;
}) {
  return (
    <Link
      href={href}
      className="nav-item"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 11,
        padding: "11px 12px",
        fontSize: 13.5,
        fontWeight: 600,
      }}
    >
      <span
        className={accent ? "brand-mark" : undefined}
        style={{
          width: 28,
          height: 28,
          borderRadius: 9,
          display: "grid",
          placeItems: "center",
          flexShrink: 0,
          background: accent ? undefined : "var(--surface-2)",
          color: accent ? "#fff" : "var(--text-muted)",
        }}
      >
        <Icon name={icon} size={15} />
      </span>
      <span style={{ flex: 1 }}>{title}</span>
      <Icon name="chevronRight" size={15} style={{ color: "var(--text-dim)" }} />
    </Link>
  );
}

function HenryWeeklyCheckinCard({ tick }: { tick: number }) {
  const { t } = useLocale();
  const [data, setData] = useState<WeeklyCheckin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getWeeklyCheckin({
      teamId: activeTeamId(),
      memberUserId: activeMemberUserId(),
    })
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  if (loading || error || !data) return null;

  return (
    <div
      style={{
        position: "relative",
        padding: "18px 20px",
        borderRadius: 16,
        border: "1px solid var(--glass-bd2)",
        background: "var(--surface)",
        marginBottom: 16,
        display: "flex",
        gap: 14,
        alignItems: "flex-start",
      }}
    >
      <HenryAvatar size={40} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          className="eyebrow"
          style={{ marginBottom: 6 }}
        >
          {t("dashboard.checkin.eyebrow")}
        </div>
        <div
          style={{
            fontSize: 14,
            color: "var(--text)",
            lineHeight: 1.55,
            marginBottom: data.highlights.length > 0 ? 12 : 0,
          }}
        >
          {data.summary}
        </div>
        {data.highlights.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
            }}
          >
            {data.highlights.map((h, i) => (
              <span
                key={i}
                className="chip chip-accent"
                style={{ fontSize: 11.5 }}
              >
                {h}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function QuotaWidget({ tick }: { tick: number }) {
  const { t } = useLocale();
  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    let cancelled = false;
    getMyProfile()
      .then((p) => {
        if (!cancelled) setProfile(p);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tick]);

  if (!profile || profile.queries_limit <= 0) return null;
  const used = profile.queries_used;
  const limit = profile.queries_limit;
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const warn = pct >= 80;
  const danger = pct >= 95;
  const barColor = danger
    ? "var(--cold)"
    : warn
      ? "var(--warm)"
      : "var(--accent)";
  return (
    <div
      className="card"
      style={{
        padding: "16px 20px",
        marginBottom: 16,
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 2 }}>
            {t("dashboard.quota.eyebrow")}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.4 }}>
            {t("dashboard.quota.subtitle", {
              used: used.toString(),
              limit: limit.toString(),
            })}
          </div>
        </div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: barColor,
            fontFamily: "var(--font-mono)",
          }}
        >
          {pct}%
        </div>
      </div>
      <div
        style={{
          width: "100%",
          height: 6,
          background: "var(--surface-2)",
          borderRadius: 999,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: danger || warn ? barColor : "var(--gradient3)",
            transition: "width .25s ease",
          }}
        />
      </div>
    </div>
  );
}

function TodayTasksWidget({ tick }: { tick: number }) {
  const { t } = useLocale();
  const [tasks, setTasks] = useState<LeadTask[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listMyTasks({ openOnly: true })
      .then((r) => !cancelled && setTasks(r.items))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tick, refreshTick]);

  if (tasks === null || tasks.length === 0) return null;

  // Tasks today + overdue first; everything else under "later".
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const dueSoon = tasks.filter(
    (t) =>
      !t.due_at || new Date(t.due_at).getTime() - now < dayMs,
  );
  const later = tasks.filter(
    (t) => t.due_at && new Date(t.due_at).getTime() - now >= dayMs,
  );

  const toggle = async (task: LeadTask) => {
    setBusy(true);
    try {
      await updateLeadTask(task.id, { done: !task.done_at });
      setRefreshTick((n) => n + 1);
    } catch {
      // silent
    } finally {
      setBusy(false);
    }
  };

  const fmt = (iso: string | null): string => {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const diff = d.getTime() - now;
    if (diff < 0 && Math.abs(diff) < dayMs) return t("tasks.overdue");
    if (diff < dayMs && diff >= 0) return t("tasks.today");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };

  return (
    <div className="card" style={{ padding: 18, marginBottom: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 700 }}>
          {t("tasks.todayTitle")}
        </div>
        <span
          className="chip"
          style={{ fontSize: 11, padding: "2px 8px" }}
        >
          {tasks.length}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {[...dueSoon, ...later].slice(0, 8).map((task) => {
          const dueLabel = fmt(task.due_at);
          const overdue =
            !task.done_at &&
            task.due_at &&
            new Date(task.due_at).getTime() < now;
          return (
            <div
              key={task.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "6px 10px",
                background: "var(--surface-2)",
                borderRadius: 8,
              }}
            >
              <button
                type="button"
                disabled={busy}
                onClick={() => toggle(task)}
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: 5,
                  border: "1px solid var(--border-strong)",
                  background: "var(--surface)",
                  cursor: "pointer",
                  padding: 0,
                  flexShrink: 0,
                }}
                aria-label={t("tasks.markDone")}
              />
              <div
                style={{
                  flex: 1,
                  fontSize: 13,
                  color: "var(--text)",
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {task.content}
              </div>
              {dueLabel && (
                <span
                  style={{
                    fontSize: 11,
                    color: overdue ? "var(--cold)" : "var(--text-muted)",
                    flexShrink: 0,
                  }}
                >
                  {dueLabel}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
