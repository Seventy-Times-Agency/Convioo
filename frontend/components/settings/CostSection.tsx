"use client";

import { useEffect, useState } from "react";
import {
  getTeamUsage,
  listMyTeams,
  setTeamCostCap,
  type TeamUsage,
} from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

/** Учёт затрат команды: месячный счётчик по сервисам, себестоимость
 * лида и потолок $ (редактирует только владелец). */
export function CostSection() {
  const { t } = useLocale();
  const [teamId, setTeamId] = useState<string | null>(() => {
    const w = getActiveWorkspace();
    return w.kind === "team" ? w.team_id : null;
  });
  const [usage, setUsage] = useState<TeamUsage | null>(null);
  const [isOwner, setIsOwner] = useState(false);
  const [capDraft, setCapDraft] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(
    () =>
      subscribeWorkspace(() => {
        const w = getActiveWorkspace();
        setTeamId(w.kind === "team" ? w.team_id : null);
      }),
    [],
  );

  useEffect(() => {
    if (!teamId) {
      setUsage(null);
      return;
    }
    getTeamUsage(teamId)
      .then((u) => {
        setUsage(u);
        setCapDraft(u.cap_usd != null ? String(u.cap_usd) : "");
      })
      .catch(() => setUsage(null));
    listMyTeams()
      .then((teams) =>
        setIsOwner(
          teams.find((tm) => tm.id === teamId)?.role === "owner",
        ),
      )
      .catch(() => setIsOwner(false));
  }, [teamId]);

  if (!teamId || !usage) return null;

  const saveCap = async () => {
    setSaving(true);
    try {
      const cap = capDraft.trim() === "" ? null : Number(capDraft);
      if (cap !== null && (!Number.isFinite(cap) || cap <= 0)) {
        showError(t("cost.capInvalid"));
        return;
      }
      const updated = await setTeamCostCap(teamId, cap);
      setUsage(updated);
      showSuccess(t("cost.capSaved"));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const pct =
    usage.ratio != null ? Math.min(100, Math.round(usage.ratio * 100)) : null;

  return (
    <Card style={{ marginBottom: 20 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {t("cost.sectionEyebrow")}
      </div>
      <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 12 }}>
        {t("cost.sectionTitle")}
      </div>

      <div style={{ fontSize: 13.5, marginBottom: 6 }}>
        {usage.cap_usd != null
          ? t("cost.monthWithCap", {
              x: usage.month_cost_usd.toFixed(2),
              cap: usage.cap_usd.toFixed(0),
            })
          : t("cost.monthNoCap", { x: usage.month_cost_usd.toFixed(2) })}
      </div>
      {pct != null && (
        <div className="score-track" style={{ maxWidth: 340, marginBottom: 10 }}>
          <div
            className={
              "score-fill " +
              (usage.blocked ? "cold" : usage.warning ? "warm" : "hot")
            }
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-dim)",
          marginBottom: 14,
        }}
      >
        {t("cost.perLead", {
          x: usage.cost_per_lead_usd.toFixed(3),
        })}
      </div>

      {Object.keys(usage.cost_by_service).length > 0 && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            marginBottom: 14,
            display: "flex",
            flexDirection: "column",
            gap: 3,
          }}
        >
          {Object.entries(usage.cost_by_service)
            .sort((a, b) => b[1] - a[1])
            .map(([svc, cost]) => (
              <div key={svc}>
                {svc}: ${cost.toFixed(2)}
              </div>
            ))}
        </div>
      )}

      {isOwner ? (
        <div
          style={{
            display: "flex",
            gap: 8,
            alignItems: "flex-end",
            maxWidth: 360,
          }}
        >
          <Input
            label={t("cost.capLabel")}
            hint={t("cost.capHint")}
            type="number"
            min={1}
            value={capDraft}
            onChange={(e) => setCapDraft(e.target.value)}
            placeholder="150"
          />
          <Button size="sm" loading={saving} onClick={saveCap}>
            {t("common.save")}
          </Button>
        </div>
      ) : (
        <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
          {t("cost.ownerOnly")}
        </div>
      )}
    </Card>
  );
}
