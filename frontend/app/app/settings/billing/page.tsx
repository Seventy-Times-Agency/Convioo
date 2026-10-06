"use client";

import { useEffect, useState } from "react";
import { Card, CountUp, EmptyState, SkeletonLines } from "@/components/ui";
import { Icon } from "@/components/brand/Icon";
import {
  getTeamLedger,
  getTeamMoney,
  grantTeamTokens,
  updateTeamMoney,
  type LedgerRow,
  type TeamMoney,
} from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

const fmt = (n: number) => n.toLocaleString("ru-RU");

/** Деньги и токены — только владелец. Бюджет вводится в $ и сразу
 * превращается в лимит токенов на месяц; баланс пополняется до него
 * 1-го числа. Остановка на нуле — по желанию команды. */
export default function MoneyPage() {
  const { t, lang } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [money, setMoney] = useState<TeamMoney | null>(null);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [grantOpen, setGrantOpen] = useState(false);
  const [grantDraft, setGrantDraft] = useState("");
  const [ledger, setLedger] = useState<LedgerRow[] | null>(null);
  const [ledgerOpen, setLedgerOpen] = useState(false);

  useEffect(() => {
    if (!teamId || role !== "owner") return;
    getTeamMoney(teamId)
      .then((m) => {
        setMoney(m);
        setBudgetDraft(m.budget_usd != null ? String(m.budget_usd) : "");
      })
      .catch((e) => showError(e instanceof Error ? e.message : String(e)));
  }, [teamId, role]);

  if (!teamId) return <Card><EmptyState icon={<Icon name="settings" size={20} />} title={t("bl.noTeam")} /></Card>;
  if (role && role !== "owner") return <Card><div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("bl.ownerOnly")}</div></Card>;
  if (!money) return <Card><SkeletonLines lines={6} /></Card>;

  const draftNum = Number(budgetDraft.replace(",", "."));
  const draftValid = budgetDraft.trim() === "" || (Number.isFinite(draftNum) && draftNum >= 0);
  const draftTokens = draftValid && budgetDraft.trim() !== "" ? Math.floor(draftNum / money.token_price_usd) : 0;
  const usedPct = money.allowance > 0 ? Math.min(100, Math.round((money.spent_month / money.allowance) * 100)) : 0;
  const maxDay = Math.max(1, ...money.by_day.map((d) => d.tokens));
  const usd = (tokens: number) => `$${(tokens * money.token_price_usd).toFixed(2)}`;
  const monthName = new Date(`${money.month}-01T12:00:00`).toLocaleDateString(
    lang === "en" ? "en-US" : lang === "uk" ? "uk-UA" : "ru-RU",
    { month: "long" },
  );

  const save = async (patch: Parameters<typeof updateTeamMoney>[1]) => {
    setSaving(true);
    try {
      const m = await updateTeamMoney(teamId, patch);
      setMoney(m);
      setBudgetDraft(m.budget_usd != null ? String(m.budget_usd) : "");
      showSuccess(t("common.saved"));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const grant = async () => {
    const n = Math.floor(Number(grantDraft));
    if (!n || n < 1) return;
    try {
      setMoney(await grantTeamTokens(teamId, n));
      setGrantDraft("");
      setGrantOpen(false);
      showSuccess(t("mn.granted", { n }));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const openLedger = async () => {
    setLedgerOpen((v) => !v);
    if (!ledger) getTeamLedger(teamId).then(setLedger).catch(() => setLedger([]));
  };

  const toggle = (on: boolean, onClick: () => void, label: string) => (
    <button type="button" onClick={onClick} disabled={saving} className="st-toggle-row">
      <span className={"st-switch" + (on ? " on" : "")} />
      <span>{label}</span>
    </button>
  );

  return (
    <div className="st-grid-2" style={{ gridTemplateColumns: "1.25fr 1fr" }}>
      <div className="st-col">
        <Card>
          <div className="eyebrow" style={{ marginBottom: 8 }}>{t("mn.balance")}</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 32, fontWeight: 800, fontVariantNumeric: "tabular-nums", color: money.balance < 0 ? "var(--cold)" : "var(--text)" }}>
              <CountUp value={money.balance} format={(n) => fmt(Math.round(n))} />
            </span>
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
              {t("mn.balanceHint", { usd: usd(Math.max(0, money.balance)), leads: fmt(Math.max(0, money.balance)) })}
            </span>
          </div>
          {money.allowance > 0 && (
            <>
              <div className="score-track" style={{ margin: "12px 0 6px" }}>
                <div className={"score-fill " + (usedPct >= 100 ? "cold" : usedPct >= 80 ? "warm" : "hot")} style={{ width: `${usedPct}%` }} />
              </div>
              <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                {t("mn.usedOf", { used: fmt(money.spent_month), all: fmt(money.allowance), month: monthName })}
              </div>
            </>
          )}
          {money.allowance === 0 && (
            <div style={{ fontSize: 12.5, color: "var(--warm)", marginTop: 8 }}>{t("mn.noBudget")}</div>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setGrantOpen((v) => !v)}>
              <Icon name="plus" size={12} /> {t("mn.grant")}
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void openLedger()}>
              {t("mn.history")}
            </button>
          </div>
          {grantOpen && (
            <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
              <input className="input" type="number" min={1} value={grantDraft} onChange={(e) => setGrantDraft(e.target.value)} placeholder="100" style={{ width: 120 }} />
              <span style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{t("mn.tokens")}{grantDraft ? ` ≈ ${usd(Number(grantDraft) || 0)}` : ""}</span>
              <button type="button" className="btn btn-sm" onClick={() => void grant()}>{t("mn.add")}</button>
            </div>
          )}
          {ledgerOpen && (
            <div style={{ marginTop: 12, maxHeight: 240, overflowY: "auto", borderTop: "1px solid var(--border)" }}>
              {!ledger && <SkeletonLines lines={3} />}
              {ledger?.map((r, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "92px 1fr 70px 70px", gap: 8, padding: "6px 0", borderBottom: "1px solid var(--border)", fontSize: 12.5 }}>
                  <span style={{ color: "var(--text-dim)" }}>{new Date(r.at).toLocaleDateString([], { day: "numeric", month: "short" })}</span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.reason ?? r.kind}</span>
                  <span style={{ textAlign: "right", color: r.amount >= 0 ? "var(--accent)" : "var(--text)", fontVariantNumeric: "tabular-nums" }}>{r.amount > 0 ? "+" : ""}{fmt(r.amount)}</span>
                  <span style={{ textAlign: "right", color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>{fmt(r.balance_after)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <div className="eyebrow" style={{ marginBottom: 4 }}>{t("mn.budget")}</div>
          <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.5, marginBottom: 12 }}>{t("mn.budgetHint")}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div className="st-money-input">
              <span>$</span>
              <input value={budgetDraft} onChange={(e) => setBudgetDraft(e.target.value)} placeholder="50" inputMode="decimal" />
            </div>
            <span style={{ fontSize: 18, color: "var(--text-dim)" }}>=</span>
            <div className="st-money-input" style={{ background: "var(--surface-2)" }}>
              <b>{fmt(draftTokens)}</b>
              <span style={{ fontSize: 12, color: "var(--text-dim)", fontWeight: 600 }}>{t("mn.tokens")}</span>
            </div>
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("mn.rate", { price: money.token_price_usd.toFixed(3) })}</span>
          </div>
          <div style={{ display: "grid", gap: 8, marginTop: 16 }}>
            {toggle(money.stop_at_zero, () => void save({ stop_at_zero: !money.stop_at_zero }), t("mn.stopAtZero"))}
            <div style={{ fontSize: 12, color: "var(--text-dim)", marginLeft: 42 }}>
              {money.stop_at_zero ? t("mn.stopOnHint") : t("mn.stopOffHint")}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
            <button
              type="button"
              className="btn"
              disabled={saving || !draftValid}
              onClick={() =>
                void save(budgetDraft.trim() === "" ? { clear_budget: true } : { budget_usd: draftNum })
              }
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("mn.warnNote")}</span>
          </div>
        </Card>
      </div>

      <Card>
        <div className="eyebrow" style={{ marginBottom: 10 }}>{t("mn.spendMonth", { month: monthName })}</div>
        <div style={{ display: "flex", gap: 3, alignItems: "flex-end", height: 70 }}>
          {money.by_day.map((d, i) => (
            <div
              key={d.date}
              className="m-col"
              title={`${d.date.slice(8)} · ${d.tokens}`}
              style={{ ["--i" as string]: i, flex: 1, height: `${Math.max(2, Math.round((d.tokens / maxDay) * 100))}%`, background: d.tokens ? "color-mix(in srgb, var(--accent) 40%, transparent)" : "var(--surface-2)", borderRadius: 2 }}
            />
          ))}
        </div>
        <div className="eyebrow" style={{ fontSize: 10, margin: "18px 0 6px" }}>{t("mn.whatFor")}</div>
        <div className="st-row first"><span>{t("mn.kindLeads")}</span><span>{fmt(money.by_kind.leads)} · {usd(money.by_kind.leads)}</span></div>
        <div className="st-row"><span>{t("mn.kindDm")}</span><span>{fmt(money.by_kind.decision_makers)} · {usd(money.by_kind.decision_makers)}</span></div>
        <div className="eyebrow" style={{ fontSize: 10, margin: "18px 0 6px" }}>{t("mn.whoSpends")}</div>
        {money.by_person.length === 0 && <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{t("mn.noSpend")}</div>}
        {money.by_person.map((p, i) => (
          <div key={p.user_id ?? `s${i}`} className={"st-row" + (i === 0 ? " first" : "")}>
            <span>{p.name}</span>
            <span>{fmt(p.tokens)}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}
