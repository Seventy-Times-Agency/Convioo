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
 * Расходы — раздел владельца. Инструмент внутренний, подписок нет:
 * экран показывает, сколько команда тратит — токены, лиды, письма и
 * затраты в долларах против потолка.
 */



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
        gridTemplateColumns: "minmax(0, 560px)",
        gap: 18,
        alignItems: "start",
      }}
      className="bl-grid"
    >
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

        <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}>
          {t("bl.internalNote")}
        </div>
      </Card>
    </div>
  );
}
