"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Card, EmptyState } from "@/components/ui";
import { roleLabel } from "@/lib/roles";
import {
  getTelephonyStatus,
  setMemberPhone,
  type TelephonyStatus,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

/**
 * Телефония: свой номер для звонков (любой участник), номера
 * команды и подключение webhook у провайдера (владелец и РОП).
 */
export default function SettingsTelephonyPage() {
  const { t } = useLocale();
  const [teamId, setTeamId] = useState<string | null>(() => activeTeamId() ?? null);
  const [status, setStatus] = useState<TelephonyStatus | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [tick, setTick] = useState(0);

  useEffect(
    () => subscribeWorkspace(() => setTeamId(activeTeamId() ?? null)),
    [],
  );

  useEffect(() => {
    if (!teamId) return;
    getTelephonyStatus(teamId)
      .then((s) => {
        setStatus(s);
        const me = getCurrentUser();
        const d: Record<number, string> = {};
        for (const m of s.members) d[m.user_id] = m.phone_extension ?? "";
        if (me && !(me.user_id in d)) d[me.user_id] = s.my_extension ?? "";
        setDrafts(d);
      })
      .catch(() => setStatus(null));
  }, [teamId, tick]);

  if (!teamId) {
    return (
      <Card>
        <EmptyState
          icon={<Icon name="phone" size={20} />}
          title={t("funnels.noTeamTitle")}
          hint={t("tel.noTeam")}
        />
      </Card>
    );
  }
  if (!status) return null;

  const me = getCurrentUser();
  const save = async (userId: number) => {
    try {
      await setMemberPhone(teamId, userId, (drafts[userId] ?? "").trim());
      showSuccess(t("tel.saved"));
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const phoneRow = (userId: number, name: string, role?: string) => (
    <div
      key={userId}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 0",
        borderTop: "1px solid var(--border)",
        flexWrap: "wrap",
      }}
    >
      <span style={{ minWidth: 160, fontSize: 13, fontWeight: 700 }}>
        {name}
        {role && (
          <span style={{ fontWeight: 500, color: "var(--text-dim)", marginLeft: 6, fontSize: 11.5 }}>
            {roleLabel(t, role)}
          </span>
        )}
      </span>
      <input
        className="input"
        value={drafts[userId] ?? ""}
        onChange={(e) => setDrafts((d) => ({ ...d, [userId]: e.target.value }))}
        placeholder={t("tel.phonePh")}
        style={{ width: 220, fontSize: 13 }}
      />
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => void save(userId)}>
        {t("common.save")}
      </button>
    </div>
  );

  const Dot = ({ on }: { on: boolean }) => (
    <span
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: on ? "var(--accent)" : "var(--text-dim)",
        display: "inline-block",
        marginRight: 6,
      }}
    />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Card>
        <div className="eyebrow" style={{ marginBottom: 10 }}>{t("tel.statusTitle")}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13 }}>
          <div>
            <Dot on={status.enabled} />
            {status.enabled
              ? t("tel.providerOn", { provider: status.provider ?? "" })
              : t("tel.providerOff")}
          </div>
          <div>
            <Dot on={status.transcription} />
            {status.transcription ? t("tel.sttOn") : t("tel.sttOff")}
          </div>
        </div>
        {!status.enabled && (
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 10, lineHeight: 1.5 }}>
            {t("tel.howToEnable")}
          </div>
        )}
      </Card>

      <Card>
        <div className="eyebrow" style={{ marginBottom: 6 }}>{t("tel.myPhoneTitle")}</div>
        <div style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 6, lineHeight: 1.5 }}>
          {t("tel.myPhoneHint")}
        </div>
        {me && phoneRow(me.user_id, t("tel.me"))}
      </Card>

      {status.members.length > 0 && (
        <Card>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("tel.teamPhonesTitle")}</div>
          {status.members
            .filter((m) => m.user_id !== me?.user_id)
            .map((m) => phoneRow(m.user_id, m.name, m.role))}
        </Card>
      )}

      {status.webhook_url && (
        <Card>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("tel.webhookTitle")}</div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.55, marginBottom: 8 }}>
            {t("tel.webhookHint")}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <code
              style={{
                fontSize: 11.5,
                background: "var(--surface-2)",
                padding: "6px 8px",
                borderRadius: 6,
                wordBreak: "break-all",
                flex: 1,
                minWidth: 240,
              }}
            >
              {status.webhook_url}
            </code>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                void navigator.clipboard?.writeText(status.webhook_url ?? "");
                showSuccess(t("tel.copied"));
              }}
            >
              {t("tel.copy")}
            </button>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 10 }}>
            {t("tel.webhookParams")}{" "}
            <code style={{ fontSize: 11.5 }}>{status.webhook_params.join(", ")}</code>
          </div>
        </Card>
      )}
    </div>
  );
}
