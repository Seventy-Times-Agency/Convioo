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
export function CostEstimateLine({ leads = 50 }: { leads?: number }) {
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
    getSearchEstimate(leads)
      .then(setEstimate)
      .catch(() => setEstimate(null));
  }, [leads]);

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
        textAlign: "center",
      }}
    >
      {estimate && (
        <div>
          {t("cost.estimate", {
            n: estimate.leads,
            x: estimate.cost_usd.toFixed(2),
          })}
        </div>
      )}
      {usage && (
        <div
          style={{
            color: usage.blocked
              ? "var(--cold)"
              : usage.warning
                ? "var(--warm)"
                : "var(--text-dim)",
          }}
        >
          {usage.cap_usd != null
            ? t("cost.monthWithCap", {
                x: usage.month_cost_usd.toFixed(2),
                cap: usage.cap_usd.toFixed(0),
              })
            : t("cost.monthNoCap", {
                x: usage.month_cost_usd.toFixed(2),
              })}
          {usage.blocked && ` · ${t("cost.blocked")}`}
        </div>
      )}
    </div>
  );
}
