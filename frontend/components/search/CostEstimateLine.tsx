"use client";

import { useEffect, useState } from "react";
import {
  getSearchEstimate,
  getTeamUsage,
  type SearchEstimate,
  type TeamUsage,
} from "@/lib/api";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

/** «~N лидов · ~$X с полным досье» + счётчик месяца против потолка
 * (командный режим, manager+). Самодостаточный — сам ходит в API,
 * ничего не ломает, если доступа к тратам нет (селз). */
export function CostEstimateLine({
  leads = 50,
  findDecisionMakers = false,
  inline = false,
}: {
  leads?: number;
  findDecisionMakers?: boolean;
  /** Строка в подвале формы (макет): без центрирования, в один ряд. */
  inline?: boolean;
}) {
  const { t } = useLocale();
  const [estimate, setEstimate] = useState<SearchEstimate | null>(null);
  const [usage, setUsage] = useState<TeamUsage | null>(null);
  const [teamId, setTeamId] = useState<string | null>(() => {
    const w = getActiveWorkspace();
    return w.kind === "team" ? w.team_id : null;
  });

  useEffect(
    () =>
      subscribeWorkspace(() => {
        const w = getActiveWorkspace();
        setTeamId(w.kind === "team" ? w.team_id : null);
      }),
    [],
  );

  useEffect(() => {
    getSearchEstimate(leads, findDecisionMakers)
      .then(setEstimate)
      .catch(() => setEstimate(null));
  }, [leads, findDecisionMakers]);

  useEffect(() => {
    if (!teamId) {
      setUsage(null);
      return;
    }
    getTeamUsage(teamId)
      .then(setUsage)
      .catch(() => setUsage(null)); // селз/нет прав — просто скрываем
  }, [teamId]);

  if (!estimate && !usage) return null;

  return (
    <div
      style={{
        fontSize: 12.5,
        color: "var(--text-muted)",
        lineHeight: 1.5,
        textAlign: inline ? "left" : "center",
        display: inline ? "flex" : undefined,
        gap: inline ? 14 : undefined,
        flexWrap: "wrap",
        alignItems: "baseline",
      }}
    >
      {estimate && (
        <div style={{ fontWeight: 700, color: "var(--text)" }}>
          {t(
            findDecisionMakers
              ? "cost.estimateTokensDm"
              : "cost.estimateTokens",
            {
              n: estimate.leads,
              tokens: estimate.tokens,
              per: estimate.tokens_per_lead,
            },
          )}
        </div>
      )}
      {usage && estimate && (
        <div
          style={{
            color:
              usage.token_balance - estimate.tokens < 0
                ? "var(--warm)"
                : usage.blocked
                  ? "var(--cold)"
                  : "var(--text-dim)",
          }}
        >
          {t("cost.balanceLeft", {
            balance: usage.token_balance,
            left: usage.token_balance - estimate.tokens,
          })}
          {usage.token_balance - estimate.tokens < 0 &&
            ` · ${t("cost.notEnough")}`}
          {usage.blocked && ` · ${t("cost.blocked")}`}
        </div>
      )}
      {usage && !estimate && (
        <div style={{ color: "var(--text-dim)" }}>
          {t("cost.balanceTokens", { tokens: usage.token_balance })}
        </div>
      )}
    </div>
  );
}
