"use client";

import { useEffect, useState } from "react";
import { Card, CountUp, SkeletonLines } from "@/components/ui";
import { getTeamEconomics, type EconomicsSearch, type TeamEconomics, type WasteReason } from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/** Причины «сгорело» в порядке показа и их цвет. */
const REASONS: { key: WasteReason; color: string }[] = [
  { key: "duplicates", color: "var(--border-strong)" },
  { key: "excluded", color: "var(--cold)" },
  { key: "failed", color: "var(--warm)" },
  { key: "prefiltered", color: "var(--ec-filter)" },
  { key: "language", color: "color-mix(in srgb, var(--ec-filter) 60%, var(--surface-3))" },
  { key: "no_contact", color: "color-mix(in srgb, var(--ec-filter) 45%, var(--surface-3))" },
  { key: "over_limit", color: "color-mix(in srgb, var(--ec-filter) 35%, var(--surface-3))" },
  { key: "nothing_found", color: "var(--text-dim)" },
];

const PERIODS = [7, 30, 90] as const;

const usd = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : `$${n.toFixed(n !== 0 && Math.abs(n) < 0.1 ? 3 : digits)}`;

/** Название сервиса по-человечески; неизвестный (новый) — как есть. */
export function useServiceLabel() {
  const { t } = useLocale();
  return (service: string) => {
    const key = `svc.${service}` as TranslationKey;
    const label = t(key);
    return label === key ? service : label;
  };
}

/** Реальные расходы платформы на команду: всего, на результат,
 * сгоревшее с причинами, по сервисам и по запускам. Владелец и техник. */
export function CostsPanel({ teamId }: { teamId: string }) {
  const { t } = useLocale();
  const svc = useServiceLabel();
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30);
  const [eco, setEco] = useState<TeamEconomics | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    getTeamEconomics(teamId, days)
      .then((e) => !cancelled && setEco(e))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [teamId, days]);

  if (failed) return <Card><div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("ec.loadFailed")}</div></Card>;
  if (!eco) return <Card><SkeletonLines lines={5} /></Card>;

  const pct = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);
  const reasons = REASONS.filter((r) => (eco.wasted_by_reason[r.key] ?? 0) > 0);
  const requested = eco.searches.reduce((s, q) => s + (q.requested ?? 0), 0);
  const empty = eco.total_usd === 0 && eco.searches.every((q) => q.cost_usd == null);

  return (
    <div className="st-col">
      <Card>
        <div className="ec-head">
          <div>
            <div className="eyebrow">{t("ec.title")}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 2 }}>{t("ec.hint")}</div>
          </div>
          <div className="seg" role="group" aria-label={t("ec.period")}>
            {PERIODS.map((d) => (
              <button key={d} type="button" className={d === days ? "active" : ""} onClick={() => setDays(d)}>
                {t("ec.days", { n: d })}
              </button>
            ))}
          </div>
        </div>
        {empty ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 12 }}>{t("ec.empty")}</div>
        ) : (
          <div className="ec-kpis">
            <div className="ec-kpi">
              <div className="eyebrow">{t("ec.total")}</div>
              <div className="v"><CountUp value={eco.total_usd} format={(n) => usd(n)} /></div>
              <div className="h">{t("ec.totalHint", { search: usd(eco.search_usd), other: usd(eco.other_usd) })}</div>
            </div>
            <div className="ec-kpi">
              <div className="eyebrow">{t("ec.useful")}</div>
              <div className="v" style={{ color: "var(--accent)" }}><CountUp value={eco.useful_usd} format={(n) => usd(n)} /></div>
              <div className="h">{t("ec.ofSearch", { p: pct(eco.useful_usd, eco.search_usd) })}</div>
            </div>
            <div className="ec-kpi">
              <div className="eyebrow">{t("ec.wasted")}</div>
              <div className="v" style={{ color: eco.wasted_usd > 0 ? "var(--cold)" : undefined }}><CountUp value={eco.wasted_usd} format={(n) => usd(n)} /></div>
              <div className="h">{t("ec.ofSearch", { p: pct(eco.wasted_usd, eco.search_usd) })}</div>
            </div>
            <div className="ec-kpi">
              <div className="eyebrow">{t("ec.delivered")}</div>
              <div className="v"><CountUp value={eco.delivered} format={(n) => Math.round(n).toLocaleString("ru-RU")} /></div>
              <div className="h">{requested > 0 ? t("ec.ofRequested", { n: requested.toLocaleString("ru-RU") }) : " "}</div>
            </div>
            <div className="ec-kpi">
              <div className="eyebrow">{t("ec.perLead")}</div>
              <div className="v">{usd(eco.all_in_per_lead_usd, 3)}</div>
              <div className="h">{t("ec.perLeadHint")}</div>
            </div>
          </div>
        )}
      </Card>

      {!empty && (
        <div className="st-grid-2">
          <Card>
            <div className="eyebrow" style={{ marginBottom: 4 }}>{t("ec.whereBurned")}</div>
            {reasons.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 6 }}>{t("ec.nothingBurned")}</div>
            ) : (
              <>
                <div className="ec-bar" role="img" aria-label={reasons.map((r) => `${t(`ec.r.${r.key}` as TranslationKey)} ${usd(eco.wasted_by_reason[r.key])}`).join(", ")}>
                  {reasons.map((r, i) => (
                    <i key={r.key} className="m-bar" style={{ ["--i" as string]: i, width: `${pct(eco.wasted_by_reason[r.key] ?? 0, eco.wasted_usd)}%`, background: r.color }} />
                  ))}
                </div>
                {reasons.map((r, i) => (
                  <div key={r.key} className={"st-row" + (i === 0 ? " first" : "")}>
                    <span className="ec-label"><i className="ec-sw" style={{ background: r.color }} />{t(`ec.r.${r.key}` as TranslationKey)}</span>
                    <span className="ec-num">{usd(eco.wasted_by_reason[r.key])}</span>
                  </div>
                ))}
              </>
            )}
            <div className="ec-note">{t("ec.splitNote")}</div>
          </Card>
          <Card>
            <div className="eyebrow" style={{ marginBottom: 4 }}>{t("ec.byService")}</div>
            {eco.by_service.filter((s) => s.cost_usd > 0).map((s, i) => (
              <div key={s.service} className={"st-row" + (i === 0 ? " first" : "")}>
                <span>{svc(s.service)}</span>
                <span className="ec-num">{usd(s.cost_usd)}</span>
              </div>
            ))}
            <div className="ec-note">{t("ec.pricesNote")}</div>
          </Card>
        </div>
      )}

      {eco.searches.length > 0 && (
        <Card>
          <div className="ec-head">
            <div className="eyebrow">{t("ec.runs")}</div>
            <div className="ec-legend">
              <span><i className="ec-sw" style={{ background: "var(--accent)" }} />{t("ec.l.delivered")}</span>
              <span><i className="ec-sw" style={{ background: "var(--border-strong)" }} />{t("ec.l.dupes")}</span>
              <span><i className="ec-sw" style={{ background: "var(--ec-filter)" }} />{t("ec.l.filtered")}</span>
              <span><i className="ec-sw" style={{ background: "var(--cold)" }} />{t("ec.l.excluded")}</span>
            </div>
          </div>
          <div className="ec-table-wrap">
            <table className="ec-table">
              <thead>
                <tr>
                  <th>{t("ec.c.run")}</th>
                  <th>{t("ec.c.result")}</th>
                  <th>{t("ec.c.found")}</th>
                  <th>{t("ec.c.funnel")}</th>
                  <th className="r">{t("ec.c.spent")}</th>
                  <th className="r">{t("ec.c.burned")}</th>
                  <th className="r">{t("ec.c.perLead")}</th>
                </tr>
              </thead>
              <tbody>
                {eco.searches.map((q) => <RunRow key={q.id} q={q} />)}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function RunRow({ q }: { q: EconomicsSearch }) {
  const { t } = useLocale();
  const f = q.funnel;
  const found = f.found ?? 0;
  const filtered = (f.prefiltered ?? 0) + (f.language ?? 0) + (f.no_contact ?? 0) + (f.over_limit ?? 0);
  const parts = [
    { n: q.delivered, c: "var(--accent)" },
    { n: f.duplicates ?? 0, c: "var(--border-strong)" },
    { n: filtered, c: "var(--ec-filter)" },
    { n: f.excluded ?? 0, c: "var(--cold)" },
  ];
  const sum = parts.reduce((s, p) => s + p.n, 0) || 1;
  const failedRun = q.status === "failed";
  const allDupes = q.delivered === 0 && !failedRun && (f.duplicates ?? 0) > 0;
  const running = q.status === "running" || q.status === "pending" || q.status === "queued";
  const status = running
    ? { cls: "", text: t("ec.s.running") }
    : failedRun
      ? { cls: "bad", text: t("ec.s.failed") }
      : allDupes
        ? { cls: "dup", text: t("ec.s.allDupes") }
        : q.delivered === 0
          ? { cls: "dup", text: t("ec.s.nothing") }
          : { cls: "ok", text: t("ec.s.delivered", { n: q.delivered }) };
  return (
    <tr>
      <td><b>{q.niche}</b> · {q.region}</td>
      <td><span className={"ec-st " + status.cls}>{status.text}</span></td>
      <td className="n">{found ? `${found} → ${q.delivered}` : "—"}</td>
      <td>
        {failedRun ? (
          <div className="ec-mini"><i style={{ width: "100%", background: "var(--warm)" }} /></div>
        ) : found ? (
          <div className="ec-mini">
            {parts.filter((p) => p.n > 0).map((p, i) => <i key={i} style={{ width: `${(p.n / sum) * 100}%`, background: p.c }} />)}
          </div>
        ) : (
          <span style={{ color: "var(--text-dim)" }}>—</span>
        )}
      </td>
      <td className="n r">{usd(q.cost_usd)}</td>
      <td className="n r" style={{ color: (q.wasted_usd ?? 0) > 0 ? "var(--cold)" : undefined }}>{usd(q.wasted_usd)}</td>
      <td className="n r">{q.cost_usd != null && q.delivered > 0 ? usd(q.cost_usd / q.delivered, 3) : "—"}</td>
    </tr>
  );
}
