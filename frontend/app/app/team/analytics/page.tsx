"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { BarList, DualLine } from "@/components/ui/MiniChart";
import { SalesAnalyticsView } from "@/components/team/SalesAnalyticsView";
import {
  ApiError,
  getSalesAnalytics,
  getTeamAnalytics,
  listMyTeams,
  listSquads,
  type SalesAnalytics,
  type SalesPeriod,
  type Squad,
  type TeamAnalytics,
} from "@/lib/api";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

type Tab = "sales" | "base";
const PERIOD_DAYS: Record<SalesPeriod, number> = { week: 7, month: 30, quarter: 90 };

/**
 * Аналитика команды. Две вкладки: «Продажи» (звонки, цели, воронка,
 * люди — новый эндпоинт) и «База и добыча» (поиски, лиды, скор,
 * стоимость — прежняя аналитика в компактном виде). Период и
 * подкоманда общие для обеих.
 */
export default function TeamAnalyticsPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("sales");
  const [period, setPeriod] = useState<SalesPeriod>("month");
  const [squadId, setSquadId] = useState<string | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [canPickSquad, setCanPickSquad] = useState(false);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [sales, setSales] = useState<SalesAnalytics | null>(null);
  const [base, setBase] = useState<TeamAnalytics | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    const ws = getActiveWorkspace();
    if (ws.kind !== "team") {
      router.replace("/app/team");
      return;
    }
    setTeamId(ws.team_id);
    listSquads(ws.team_id)
      .then((r) => setSquads(r.squads))
      .catch(() => setSquads([]));
    listMyTeams()
      .then((rows) => {
        const me = rows.find((r) => r.id === ws.team_id);
        setCanPickSquad(me?.role === "owner" || me?.role === "admin");
      })
      .catch(() => undefined);
  }, [router, tick]);

  useEffect(() => {
    if (!teamId) return;
    let cancelled = false;
    setLoadError(null);
    const fail = (e: unknown) => {
      if (cancelled) return;
      const msg =
        e instanceof ApiError && e.status === 403
          ? t("team.analytics.ownerOnly")
          : e instanceof Error
            ? e.message
            : String(e);
      setLoadError(msg);
      showError(msg);
    };
    if (tab === "sales") {
      setSales(null);
      getSalesAnalytics(teamId, period, squadId)
        .then((d) => !cancelled && setSales(d))
        .catch(fail);
    } else {
      setBase(null);
      const to = new Date();
      const from = new Date(to.getTime() - PERIOD_DAYS[period] * 86_400_000);
      getTeamAnalytics(teamId, { from: from.toISOString(), to: to.toISOString() })
        .then((d) => !cancelled && setBase(d))
        .catch(fail);
    }
    return () => {
      cancelled = true;
    };
  }, [teamId, tab, period, squadId, t]);

  const chip = (active: boolean, label: string, onClick: () => void) => (
    <button
      key={label}
      type="button"
      onClick={onClick}
      style={{
        padding: "4px 10px",
        fontSize: 12,
        borderRadius: 999,
        cursor: "pointer",
        border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
        background: active ? "color-mix(in srgb, var(--accent) 12%, transparent)" : "var(--surface)",
        color: active ? "var(--accent)" : "var(--text-muted)",
        fontWeight: active ? 600 : 500,
      }}
    >
      {label}
    </button>
  );

  return (
    <>
      <Topbar title={t("team.analytics.title")} subtitle={t("an.subtitle")} />
      <div className="page" style={{ maxWidth: 1240 }}>
        {/* Вкладки + период + подкоманда — одна строка управления. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderBottom: "1px solid var(--border)",
            marginBottom: 12,
            flexWrap: "wrap",
          }}
        >
          {(["sales", "base"] as Tab[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              style={{
                background: "none",
                border: "none",
                borderBottom: "2px solid " + (tab === k ? "var(--accent)" : "transparent"),
                padding: "8px 12px",
                cursor: "pointer",
                fontSize: 13.5,
                fontWeight: tab === k ? 700 : 500,
                color: tab === k ? "var(--text)" : "var(--text-muted)",
              }}
            >
              {k === "sales" ? t("an.tab.sales") : t("an.tab.base")}
            </button>
          ))}
          <div style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center", paddingBottom: 6 }}>
            {(["week", "month", "quarter"] as SalesPeriod[]).map((p) =>
              chip(period === p, t(`an.period.${p}` as const), () => setPeriod(p)),
            )}
            {tab === "sales" && canPickSquad && squads.length > 0 && (
              <select
                className="select"
                value={squadId ?? ""}
                onChange={(e) => setSquadId(e.target.value || null)}
                style={{ width: "auto", fontSize: 12, padding: "3px 8px", marginLeft: 6 }}
              >
                <option value="">{t("an.allTeam")}</option>
                {squads.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {loadError && <div style={{ fontSize: 13, color: "var(--cold)" }}>{loadError}</div>}
        {!loadError && tab === "sales" && !sales && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
        )}
        {!loadError && tab === "base" && !base && (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
        )}

        {tab === "sales" && sales && <SalesAnalyticsView data={sales} />}
        {tab === "base" && base && <BaseView data={base} />}
      </div>
    </>
  );
}

/** «База и добыча»: прежние блоки, сжатые в полосу чисел + три карточки. */
function BaseView({ data }: { data: TeamAnalytics }) {
  const { t } = useLocale();
  const hot = data.members.reduce((n, m) => n + m.hot_leads, 0);
  const tiles: [string, string | number, string][] = [
    [t("team.analytics.tile.searches"), data.searches_total, t("an.base.searchesHint")],
    [t("team.analytics.tile.leads"), data.leads_total, t("an.base.leadsHint", { hot })],
    [t("team.analytics.tile.avgScore"), data.avg_lead_score ?? "—", t("an.base.scoreHint")],
    [t("team.analytics.tile.costPerLead"), data.avg_lead_cost_usd !== null ? `$${data.avg_lead_cost_usd}` : "—", t("an.base.costHint")],
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="card an-kpi" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        {tiles.map(([label, value, hint], i) => (
          <div key={label} style={{ padding: "12px 14px", borderRight: i === 3 ? "none" : "1px solid var(--border)" }}>
            <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 24, fontWeight: 800, lineHeight: 1.1, fontVariantNumeric: "tabular-nums" }}>{value}</div>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 3 }}>{hint}</div>
          </div>
        ))}
      </div>
      <div className="card" style={{ padding: "14px 16px" }}>
        <div className="eyebrow" style={{ fontSize: 10, marginBottom: 10 }}>{t("team.analytics.activityByDay")}</div>
        <DualLine
          points={data.timeseries.map((p) => ({ label: p.date, a: p.searches_total, b: p.leads_total }))}
          aLabel={t("team.analytics.tile.searches")}
          bLabel={t("team.analytics.tile.leads")}
          height={130}
        />
      </div>
      <div className="an-3">
        <div className="card" style={{ padding: "14px 16px" }}>
          <div className="eyebrow" style={{ fontSize: 10, marginBottom: 10 }}>{t("team.analytics.statusBreakdown")}</div>
          <BarList items={data.status_breakdown.map((b) => ({ label: b.status, value: b.leads_count }))} />
        </div>
        <div className="card" style={{ padding: "14px 16px" }}>
          <div className="eyebrow" style={{ fontSize: 10, marginBottom: 10 }}>{t("team.analytics.topNiches")}</div>
          <BarList items={data.niches.map((b) => ({ label: b.niche, value: b.searches_total }))} />
        </div>
        <div className="card" style={{ padding: "14px 16px" }}>
          <div className="eyebrow" style={{ fontSize: 10, marginBottom: 10 }}>{t("team.analytics.memberActivity")}</div>
          <BarList
            items={data.members.map((m) => ({
              label: m.name,
              value: m.leads_total,
              hint: t("team.analytics.memberHint", { searches: m.searches_total, hot: m.hot_leads }),
            }))}
          />
        </div>
      </div>
    </div>
  );
}
