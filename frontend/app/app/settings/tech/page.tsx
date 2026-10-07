"use client";

import { hasFullAccess } from "@/lib/roles";
import { useEffect, useState } from "react";
import { Card, SkeletonLines } from "@/components/ui";
import { ApiKeysSection } from "@/components/settings/ApiKeysSection";
import { WebhooksSection } from "@/components/settings/WebhooksSection";
import {
  TechAccess,
  TechApiCatalog,
  TechIds,
  TechInbound,
  TechIntegrations,
  TechJobs,
  TechLimits,
  TechNetwork,
  TechOutbound,
  TechPlatform,
  techInfoAsText,
} from "@/components/settings/TechInfo";
import {
  getTeamConnections,
  getTeamUsage,
  getTechInfo,
  getTelephonyStatus,
  type TeamUsage,
  type TechInfo,
  type TelephonyStatus,
} from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";

/** Техническое — полная картина платформы для техотдела: адреса и IP,
 * доступ к API, идентификаторы, входящие и исходящие вебхуки, внешние
 * сервисы, фоновые задачи, лимиты, каталог API — плюс то, что
 * настраивают один раз (провайдер звонков, бот, ключи, вебхуки).
 * Владелец и техник. Сводку можно скачать JSON-ом или скопировать. */
export default function TechPage() {
  const { t } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [tel, setTel] = useState<TelephonyStatus | null>(null);
  const [usage, setUsage] = useState<TeamUsage | null>(null);
  const [botOn, setBotOn] = useState<boolean | null>(null);
  const [copied, setCopied] = useState(false);
  const [info, setInfo] = useState<TechInfo | null>(null);
  const [infoError, setInfoError] = useState(false);
  const [textCopied, setTextCopied] = useState(false);

  useEffect(() => {
    if (!teamId || !hasFullAccess(role)) return;
    getTelephonyStatus(teamId).then(setTel).catch(() => setTel(null));
    getTeamUsage(teamId).then(setUsage).catch(() => setUsage(null));
    getTeamConnections(teamId).then((c) => setBotOn(c.telegram_bot)).catch(() => setBotOn(null));
    getTechInfo(teamId)
      .then(setInfo)
      .catch(() => setInfoError(true));
  }, [teamId, role]);

  if (role && !hasFullAccess(role)) {
    return <Card><div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("tc.ownerOnly")}</div></Card>;
  }

  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const downloadJson = () => {
    if (!info) return;
    const blob = new Blob([JSON.stringify(info, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `convioo-tech-${info.team.id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyText = () => {
    if (!info) return;
    void navigator.clipboard?.writeText(techInfoAsText(info));
    setTextCopied(true);
    setTimeout(() => setTextCopied(false), 1500);
  };

  const telCard = (
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
  );

  const costCard = (
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
  );

  const botCard = (
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
  );

  return (
    <div className="st-col">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <div style={{ fontSize: 12, color: "var(--warm)", display: "flex", gap: 6, alignItems: "center" }}>
          <span className="st-dot wrn" /> {t("tc.note")}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn btn-ghost btn-sm" disabled={!info} onClick={copyText}>
            {textCopied ? t("tel.copied") : t("tk.copyText")}
          </button>
          <button type="button" className="btn btn-sm" disabled={!info} onClick={downloadJson}>
            {t("tk.downloadJson")}
          </button>
        </div>
      </div>

      {infoError && (
        <Card><div style={{ fontSize: 13, color: "var(--cold)" }}>{t("tk.loadError")}</div></Card>
      )}
      {!info && !infoError && <Card><SkeletonLines lines={6} /></Card>}

      {info && (
        <>
          <div className="st-grid-2">
            <TechPlatform d={info} />
            <TechNetwork d={info} />
          </div>
          <div className="st-grid-2">
            <TechAccess d={info} />
            <ApiKeysSection />
          </div>
          <TechIds d={info} />
          <TechInbound d={info} />
          <div className="st-grid-2">
            <TechOutbound d={info} />
            <WebhooksSection />
          </div>
          <TechIntegrations d={info} />
        </>
      )}

      <div className="st-grid-2">
        {telCard}
        {botCard}
      </div>

      {info ? (
        <div className="st-grid-2">
          <TechJobs d={info} />
          <div className="st-col">
            {costCard}
            <TechLimits d={info} />
          </div>
        </div>
      ) : (
        costCard
      )}

      {info && <TechApiCatalog d={info} />}
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
