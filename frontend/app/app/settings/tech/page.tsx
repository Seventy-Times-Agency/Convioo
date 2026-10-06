"use client";

import { hasFullAccess } from "@/lib/roles";
import { useEffect, useState } from "react";
import { Card, SkeletonLines } from "@/components/ui";
import { ApiKeysSection } from "@/components/settings/ApiKeysSection";
import { WebhooksSection } from "@/components/settings/WebhooksSection";
import { request } from "@/lib/api/_core";
import {
  getTeamConnections,
  getTeamUsage,
  getTelephonyStatus,
  type TeamUsage,
  type TelephonyStatus,
} from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";

/** Техническое — то, что настраивают один раз и что обычному
 * сотруднику не нужно: вебхуки провайдера звонков, бот Telegram,
 * исходящие вебхуки, API-ключи, себестоимость в $, состояние серверов.
 * Только владелец; позже — роль «технический менеджер». */
export default function TechPage() {
  const { t } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [tel, setTel] = useState<TelephonyStatus | null>(null);
  const [usage, setUsage] = useState<TeamUsage | null>(null);
  const [botOn, setBotOn] = useState<boolean | null>(null);
  const [copied, setCopied] = useState(false);
  const [health, setHealth] = useState<{ db: boolean; redis: boolean; queue_depth?: number; commit?: string } | null>(null);

  useEffect(() => {
    if (!teamId || !hasFullAccess(role)) return;
    getTelephonyStatus(teamId).then(setTel).catch(() => setTel(null));
    getTeamUsage(teamId).then(setUsage).catch(() => setUsage(null));
    getTeamConnections(teamId).then((c) => setBotOn(c.telegram_bot)).catch(() => setBotOn(null));
    request<{ db: boolean; redis: boolean; queue_depth?: number; commit?: string }>("/health")
      .then(setHealth)
      .catch(() => setHealth({ db: false, redis: false }));
  }, [teamId, role]);

  if (role && !hasFullAccess(role)) {
    return <Card><div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("tc.ownerOnly")}</div></Card>;
  }

  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="st-col">
      <div style={{ fontSize: 12, color: "var(--warm)", display: "flex", gap: 6, alignItems: "center" }}>
        <span className="st-dot wrn" /> {t("tc.note")}
      </div>
      <div className="st-grid-2">
          <Card>
            <div className="eyebrow" style={{ marginBottom: 8 }}>{t("tc.telTitle")}</div>
            {!tel && <SkeletonLines lines={3} />}
            {tel && (
              <>
                <div className="st-row first">
                  <span>{t("tc.provider")}</span>
                  <span>
                    <span className={"st-dot " + (tel.enabled ? "ok" : "off")} /> {tel.provider ?? t("tc.none")}
                    {tel.mode ? ` · ${tel.mode === "browser" ? t("tc.modeBrowser") : t("tc.modeCallback")}` : ""}
                  </span>
                </div>
                <div className="st-row"><span>{t("cm.transcription")}</span><span>{tel.transcription ? t("common.on") : t("common.off")}</span></div>
                {tel.webhook_url && (
                  <>
                    <div className="eyebrow" style={{ fontSize: 10, margin: "14px 0 6px" }}>
                      {tel.mode === "browser" ? t("tel.webhookTitleTelnyx") : t("tel.webhookTitle")}
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                      <code className="st-code">{tel.webhook_url}</code>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => copy(tel.webhook_url ?? "")}>
                        {copied ? t("tel.copied") : t("tel.copy")}
                      </button>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5, marginTop: 6 }}>
                      {tel.mode === "browser" ? t("tel.webhookHintTelnyx") : t("tel.webhookHint")}
                      {tel.webhook_params.length > 0 && (
                        <> {t("tel.webhookParams")} <code style={{ fontSize: 11.5 }}>{tel.webhook_params.join(", ")}</code></>
                      )}
                    </div>
                  </>
                )}
              </>
            )}
          </Card>
          <Card>
            <div className="eyebrow" style={{ marginBottom: 4 }}>{t("tc.costTitle")}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-dim)", marginBottom: 8 }}>{t("tc.costHint")}</div>
            {!usage && <SkeletonLines lines={4} />}
            {usage && (
              <>
                <div className="st-row first"><span>{t("tc.costMonth")}</span><b>${usage.month_cost_usd.toFixed(2)}</b></div>
                {Object.entries(groupCosts(usage.cost_by_service))
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => (
                    <div key={k} className="st-row"><span>{k}</span><span>${v.toFixed(2)}</span></div>
                  ))}
                <div className="st-row"><span>{t("tc.costPerLead")}</span><b>${usage.cost_per_lead_usd.toFixed(3)}</b></div>
              </>
            )}
          </Card>
      </div>
      <div className="st-grid-2">
          <Card>
            <div className="eyebrow" style={{ marginBottom: 8 }}>{t("tc.botTitle")}</div>
            <div className="st-row first">
              <span>{t("tc.botStatus")}</span>
              <span><span className={"st-dot " + (botOn ? "ok" : "off")} /> {botOn ? t("cn.botOn") : t("cn.botOff")}</span>
            </div>
            {!botOn && (
              <ol style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.6 }}>
                <li>{t("tc.bot1")}</li>
                <li>{t("tc.bot2")}</li>
                <li>{t("tc.bot3")}</li>
              </ol>
            )}
          </Card>
          <Card>
            <div className="eyebrow" style={{ marginBottom: 8 }}>{t("tc.platform")}</div>
            {!health && <SkeletonLines lines={3} />}
            {health && (
              <>
                <div className="st-row first"><span>{t("tc.db")}</span><span><span className={"st-dot " + (health.db ? "ok" : "bad")} />{health.db ? t("tc.ok") : t("tc.down")}</span></div>
                <div className="st-row"><span>{t("tc.queue")}</span><span><span className={"st-dot " + (health.redis ? "ok" : "bad")} />{health.redis ? t("tc.queueOk", { n: health.queue_depth ?? 0 }) : t("tc.down")}</span></div>
                <div className="st-row"><span>{t("tc.version")}</span><span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{(health.commit ?? "—").slice(0, 7)}</span></div>
              </>
            )}
          </Card>
      </div>
      <div className="st-grid-2">
        <WebhooksSection />
        <ApiKeysSection />
      </div>
    </div>
  );
}

/** Сырые ключи учёта затрат → понятные группы сервисов. */
function groupCosts(raw: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw)) {
    const name = k.startsWith("google")
      ? "Google Places"
      : k.startsWith("claude") || k.startsWith("anthropic")
        ? "ИИ (Claude)"
        : k.startsWith("deepgram") || k.startsWith("stt") || k.startsWith("whisper")
          ? "Расшифровка звонков"
          : k.startsWith("hunter")
            ? "Hunter"
            : k.startsWith("proxycurl")
              ? "Proxycurl"
              : k;
    out[name] = (out[name] ?? 0) + v;
  }
  return out;
}
