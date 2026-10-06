"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { Icon } from "@/components/brand/Icon";
import {
  createTelegramLink,
  disconnectGmail,
  disconnectOutlook,
  getGmailStatus,
  getNotificationPrefs,
  getOutlookStatus,
  getTelegramStatus,
  getTelephonyStatus,
  setMemberPhone,
  startGmailAuthorize,
  startOutlookAuthorize,
  unlinkTelegram,
  updateNotificationPrefs,
  type GmailIntegrationStatus,
  type NotificationPrefs,
  type OutlookIntegrationStatus,
  type TelegramStatus,
  type TelephonyStatus,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

const err = (e: unknown) => showError(e instanceof Error ? e.message : String(e));

/** Мои подключения — то, что каждый настраивает сам на своём аккаунте:
 * номер для звонков, почта, Telegram. Одинаково для всех ролей. */
export function MyConnections() {
  const { t } = useLocale();
  const { teamId } = useActiveTeam();
  const me = getCurrentUser();

  const [tel, setTel] = useState<TelephonyStatus | null>(null);
  const [phone, setPhone] = useState("");
  const [phoneSaved, setPhoneSaved] = useState("");
  const [gmail, setGmail] = useState<GmailIntegrationStatus | null>(null);
  const [outlook, setOutlook] = useState<OutlookIntegrationStatus | null>(null);
  const [tg, setTg] = useState<TelegramStatus | null>(null);
  const [tgCode, setTgCode] = useState<{ token: string; deep_link: string | null } | null>(null);

  const reloadTg = () => getTelegramStatus().then(setTg).catch(() => setTg(null));

  useEffect(() => {
    getGmailStatus().then(setGmail).catch(() => setGmail(null));
    getOutlookStatus().then(setOutlook).catch(() => setOutlook(null));
    void reloadTg();
  }, []);

  useEffect(() => {
    if (!teamId) return;
    getTelephonyStatus(teamId)
      .then((s) => {
        setTel(s);
        setPhone(s.my_extension ?? "");
        setPhoneSaved(s.my_extension ?? "");
      })
      .catch(() => setTel(null));
  }, [teamId]);

  // Пока ждём, что человек нажмёт Start в боте, — проверяем привязку.
  useEffect(() => {
    if (!tgCode || tg?.linked) return;
    const id = window.setInterval(() => void reloadTg(), 4000);
    return () => window.clearInterval(id);
  }, [tgCode, tg?.linked]);

  const savePhone = async () => {
    if (!teamId || !me) return;
    try {
      await setMemberPhone(teamId, me.user_id, phone.trim());
      setPhoneSaved(phone.trim());
      showSuccess(t("tel.saved"));
    } catch (e) {
      err(e);
    }
  };

  const connectMail = async (kind: "gmail" | "outlook") => {
    try {
      const { url } = kind === "gmail" ? await startGmailAuthorize() : await startOutlookAuthorize();
      window.location.href = url;
    } catch (e) {
      err(e);
    }
  };

  const disconnectMail = async (kind: "gmail" | "outlook") => {
    try {
      if (kind === "gmail") {
        await disconnectGmail();
        setGmail((g) => (g ? { ...g, connected: false, account_email: null } : g));
      } else {
        await disconnectOutlook();
        setOutlook((o) => (o ? { ...o, connected: false, account_email: null } : o));
      }
    } catch (e) {
      err(e);
    }
  };

  const linkTg = async () => {
    try {
      const r = await createTelegramLink();
      setTgCode({ token: r.token, deep_link: r.deep_link });
      if (r.deep_link) window.open(r.deep_link, "_blank", "noopener");
    } catch (e) {
      err(e);
    }
  };

  const unlinkTg = async () => {
    try {
      await unlinkTelegram();
      setTgCode(null);
      await reloadTg();
    } catch (e) {
      err(e);
    }
  };

  const mail = gmail?.connected ? { kind: "gmail" as const, email: gmail.account_email } : outlook?.connected ? { kind: "outlook" as const, email: outlook.account_email } : null;

  const head = (title: string, ok: boolean | null, okText: string, offText: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <span className="eyebrow">{title}</span>
      {ok !== null && (
        <span className={"chip" + (ok ? " st-chip-ok" : "")} style={{ marginLeft: "auto", fontSize: 11 }}>
          <span className={"st-dot " + (ok ? "ok" : "off")} />
          {ok ? okText : offText}
        </span>
      )}
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14, marginBottom: 14 }}>
      {teamId && (
        <Card padding={16}>
          {head(t("pr.phone"), tel ? !!tel.my_extension : null, t("pr.phoneSet"), t("pr.phoneNotSet"))}
          <input
            className="input"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void savePhone()}
            placeholder={t("tel.phonePh")}
            style={{ fontFamily: "var(--font-mono)", fontSize: 12.5 }}
          />
          <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5, marginTop: 6 }}>
            {tel?.mode === "browser" ? t("pr.phoneHintBrowser") : t("pr.phoneHint")}
          </div>
          {phone !== phoneSaved && (
            <button type="button" className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => void savePhone()}>
              {t("common.save")}
            </button>
          )}
        </Card>
      )}

      <Card padding={16}>
        {head(t("pr.mail"), gmail || outlook ? !!mail : null, mail?.kind === "outlook" ? "Outlook" : "Gmail", t("pr.notConnected"))}
        {mail ? (
          <>
            <div style={{ fontSize: 13, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis" }}>{mail.email}</div>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5, marginTop: 6 }}>{t("pr.mailHint")}</div>
            <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => void disconnectMail(mail.kind)}>
              {t("pr.disconnect")}
            </button>
          </>
        ) : (
          <>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5 }}>{t("pr.mailOffHint")}</div>
            <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
              <button type="button" className="btn btn-sm" onClick={() => void connectMail("gmail")}>
                <Icon name="mail" size={12} /> Gmail
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void connectMail("outlook")}>
                Outlook
              </button>
            </div>
          </>
        )}
      </Card>

      <Card padding={16}>
        {head("Telegram", tg ? tg.linked : null, t("pr.linked"), t("pr.notConnected"))}
        {tg && !tg.configured && (
          <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5 }}>{t("pr.tgNoBot")}</div>
        )}
        {tg?.configured && tg.linked && (
          <>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5 }}>
              {t("pr.tgOn", { bot: tg.bot_username ? `@${tg.bot_username}` : "" })}
            </div>
            <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => void unlinkTg()}>
              {t("pr.disconnect")}
            </button>
          </>
        )}
        {tg?.configured && !tg.linked && (
          <>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", lineHeight: 1.5 }}>{t("pr.tgOff")}</div>
            {!tgCode ? (
              <button type="button" className="btn btn-sm" style={{ marginTop: 10 }} onClick={() => void linkTg()}>
                <Icon name="send" size={12} /> {t("pr.tgConnect")}
              </button>
            ) : (
              <div style={{ marginTop: 10, fontSize: 12, lineHeight: 1.5 }}>
                {tgCode.deep_link ? (
                  <a href={tgCode.deep_link} target="_blank" rel="noreferrer" className="btn btn-sm">
                    {t("pr.tgOpen")}
                  </a>
                ) : null}
                <div style={{ color: "var(--text-dim)", marginTop: 6 }}>
                  {t("pr.tgCode")} <code style={{ fontWeight: 800 }}>/start {tgCode.token}</code>
                </div>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}

/** Уведомления — личные: утренняя сводка и отслеживание ответов. */
export function MyNotifications() {
  const { t } = useLocale();
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  useEffect(() => {
    getNotificationPrefs().then(setPrefs).catch(() => setPrefs(null));
  }, []);
  if (!prefs) return null;
  const flip = async (key: "daily_digest_enabled" | "email_reply_tracking_enabled") => {
    const next = !prefs[key];
    setPrefs({ ...prefs, [key]: next });
    try {
      setPrefs(await updateNotificationPrefs({ [key]: next }));
    } catch (e) {
      setPrefs({ ...prefs, [key]: !next });
      err(e);
    }
  };
  const row = (key: "daily_digest_enabled" | "email_reply_tracking_enabled", title: string, desc: string, first?: boolean) => (
    <div className={"st-row" + (first ? " first" : "")} style={{ alignItems: "flex-start" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, color: "var(--text)" }}>{title}</div>
        <div style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.45, marginTop: 2 }}>{desc}</div>
      </div>
      <button type="button" className="st-toggle-row" onClick={() => void flip(key)} aria-pressed={prefs[key]}>
        <span className={"st-switch" + (prefs[key] ? " on" : "")} />
      </button>
    </div>
  );
  return (
    <Card padding={16} style={{ marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>{t("settings.tab.notifications")}</div>
      {row("daily_digest_enabled", t("settings.notifications.digest.title"), t("settings.notifications.digest.desc"), true)}
      {row(
        "email_reply_tracking_enabled",
        t("settings.notifications.replyTracking.title"),
        prefs.email_reply_last_checked_at
          ? t("settings.notifications.replyTracking.lastChecked", { when: new Date(prefs.email_reply_last_checked_at).toLocaleString() })
          : t("settings.notifications.replyTracking.desc"),
      )}
    </Card>
  );
}
