"use client";

import { useEffect, useState } from "react";
import { Card, EmptyState } from "@/components/ui";
import { Icon } from "@/components/Icon";
import {
  getTeamDetail,
  getTeamUsage,
  type TeamUsage,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/**
 * Биллинг — Billing.dc.html, раздел владельца. Инстанс внутренний,
 * биллинг выключен — экран честно говорит об этом и показывает
 * реальное использование: токены, лиды, письма, затраты добычи.
 * Цифры тарифов — заготовка SaaS-режима; цену токена назначим,
 * сравнив её с внутренней себестоимостью.
 */

interface Plan {
  id: string;
  name: string;
  price: number;
  desc: TranslationKey;
}

const PLANS: Plan[] = [
  { id: "solo", name: "Solo", price: 49, desc: "bl.plan.solo.desc" },
  { id: "team", name: "Team", price: 149, desc: "bl.plan.team.desc" },
  { id: "agency", name: "Agency", price: 349, desc: "bl.plan.agency.desc" },
];

function UsageBar({
  label,
  value,
  max,
  hint,
  fmt,
}: {
  label: string;
  value: number;
  max: number | null;
  hint: string;
  fmt?: (v: number) => string;
}) {
  const show = fmt ?? ((v: number) => String(v));
  const ratio =
    max && max > 0 ? Math.min(1, Math.max(0, value / max)) : null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 13,
          gap: 8,
        }}
      >
        <span style={{ fontWeight: 700 }}>{label}</span>
        <span
          style={{
            color: "var(--text-muted)",
            fontVariantNumeric: "tabular-nums",
            whiteSpace: "nowrap",
          }}
        >
          {show(value)}
          {max != null ? ` / ${show(max)}` : ""}
        </span>
      </div>
      {ratio != null && (
        <div
          style={{
            height: 6,
            borderRadius: 3,
            background: "var(--surface-2)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${Math.round(ratio * 100)}%`,
              height: "100%",
              background:
                ratio >= 1 ? "var(--cold)" : "var(--accent)",
            }}
          />
        </div>
      )}
      <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
        {hint}
      </span>
    </div>
  );
}

export default function SettingsBillingPage() {
  const { t } = useLocale();
  const [teamId, setTeamId] = useState<string | null>(
    () => activeTeamId() ?? null,
  );
  const [role, setRole] = useState<string | null>(null);
  const [plan, setPlan] = useState<string | null>(null);
  const [usage, setUsage] = useState<TeamUsage | null>(null);

  useEffect(
    () => subscribeWorkspace(() => setTeamId(activeTeamId() ?? null)),
    [],
  );

  useEffect(() => {
    if (!teamId) return;
    getTeamDetail(teamId)
      .then((d) => {
        setRole(d.role);
        setPlan(d.plan);
      })
      .catch(() => setRole(null));
    getTeamUsage(teamId)
      .then(setUsage)
      .catch(() => setUsage(null));
  }, [teamId]);

  if (!teamId) {
    return (
      <Card>
        <EmptyState
          icon={<Icon name="settings" size={20} />}
          title={t("st.tab.billing")}
          hint={t("bl.noTeam")}
        />
      </Card>
    );
  }
  if (role !== null && role !== "owner") {
    return (
      <Card>
        <EmptyState
          icon={<Icon name="settings" size={20} />}
          title={t("st.tab.billing")}
          hint={t("bl.ownerOnly")}
        />
      </Card>
    );
  }

  const num = (v: number) => v.toLocaleString("ru-RU");

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) minmax(280px, 420px)",
        gap: 18,
        alignItems: "start",
      }}
      className="bl-grid"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
        <div
          style={{
            border: "1.5px dashed var(--border)",
            borderRadius: 12,
            padding: "13px 18px",
            fontSize: 13,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {t("bl.offNotice")}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: 12,
          }}
        >
          {PLANS.map((p) => {
            const current = plan === p.id;
            return (
              <Card
                key={p.id}
                style={
                  current
                    ? {
                        border: "1.5px solid var(--accent)",
                        boxShadow:
                          "0 4px 14px -6px color-mix(in srgb, var(--accent) 25%, transparent)",
                      }
                    : undefined
                }
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 10,
                  }}
                >
                  <span style={{ fontSize: 15, fontWeight: 800 }}>
                    {p.name}
                  </span>
                  {current && (
                    <span
                      style={{
                        fontSize: 10.5,
                        fontWeight: 800,
                        color: "var(--accent)",
                        background: "var(--accent-soft)",
                        borderRadius: 10,
                        padding: "2px 10px",
                      }}
                    >
                      {t("bl.current")}
                    </span>
                  )}
                </div>
                <div
                  style={{
                    fontSize: 24,
                    fontWeight: 800,
                    marginBottom: 10,
                  }}
                >
                  ${p.price}
                  <span
                    style={{
                      fontSize: 13,
                      color: "var(--text-dim)",
                      fontWeight: 600,
                    }}
                  >
                    {" "}
                    {t("bl.perMonth")}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 12.5,
                    color: "var(--text-muted)",
                    lineHeight: 1.6,
                  }}
                >
                  {t(p.desc)}
                </div>
              </Card>
            );
          })}
        </div>

        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-dim)",
          }}
        >
          {t("bl.tokenHint")}
        </div>

        <Card>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            {t("bl.invoices")}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
            {t("bl.invoicesEmpty")}
          </div>
        </Card>
      </div>

      <Card
        style={{ display: "flex", flexDirection: "column", gap: 16 }}
      >
        <div className="eyebrow">{t("bl.usage")}</div>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 700 }}>
              {t("bl.tokens")}
            </span>
            <span
              style={{
                fontSize: 22,
                fontWeight: 800,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {usage ? num(usage.token_balance) : "—"}
              <span
                style={{
                  fontSize: 12,
                  color: "var(--text-dim)",
                  fontWeight: 600,
                }}
              >
                {" "}
                {t("bl.balance")}
              </span>
            </span>
          </div>
          {usage && (
            <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
              {t("bl.spentMonth", { n: num(usage.tokens_spent_month) })}
            </span>
          )}
        </div>

        {usage && (
          <>
            <UsageBar
              label={t("bl.leads")}
              value={usage.leads_month}
              max={null}
              hint={t("bl.leadsHint")}
              fmt={num}
            />
            <UsageBar
              label={t("bl.emails")}
              value={usage.emails_month}
              max={null}
              hint={t("bl.emailsHint")}
              fmt={num}
            />
            <UsageBar
              label={t("bl.spend")}
              value={usage.month_cost_usd}
              max={usage.cap_usd}
              hint={t("bl.spendHint")}
              fmt={(v) => `$${v.toFixed(2).replace(/\.00$/, "")}`}
            />
          </>
        )}

        <div
          style={{
            marginTop: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <button
            type="button"
            className="btn btn-ghost"
            disabled
            style={{ justifyContent: "center" }}
          >
            {t("bl.topup")} · {t("bl.soon")}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled
            style={{ justifyContent: "center" }}
          >
            {t("bl.changePlan")} · {t("bl.soon")}
          </button>
        </div>
      </Card>
    </div>
  );
}
