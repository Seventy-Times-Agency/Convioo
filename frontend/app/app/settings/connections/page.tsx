"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, SkeletonLines } from "@/components/ui";
import { Avatar } from "@/components/ui";
import { Icon } from "@/components/brand/Icon";
import { getTeamConnections, type MemberConnections } from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";
import { roleLabel } from "@/lib/roles";

/** Подключения. Сверху — общие для всей команды (бот Telegram
 * компании, Agency OS). Ниже — личные: у каждого сотрудника своя
 * почта и свой Telegram; подключает сам человек в профиле, здесь
 * руководитель только видит, у кого что готово. */
export default function ConnectionsPage() {
  const { t } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [data, setData] = useState<{ telegram_bot: boolean; members: MemberConnections[] } | null>(null);

  useEffect(() => {
    if (!teamId) return;
    getTeamConnections(teamId).then(setData).catch(() => setData({ telegram_bot: false, members: [] }));
  }, [teamId]);

  const status = (ok: boolean, okText: string, offText: string) => (
    <span className={"chip" + (ok ? " st-chip-ok" : "")} style={{ fontSize: 11.5 }}>
      <span className={"st-dot " + (ok ? "ok" : "off")} />
      {ok ? okText : offText}
    </span>
  );

  const card = (
    icon: React.ReactNode,
    title: string,
    desc: string,
    right: React.ReactNode,
    footer?: React.ReactNode,
  ) => (
    <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div className="st-icon">{icon}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 800 }}>{title}</div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5, marginTop: 2 }}>{desc}</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: "auto" }}>
        {right}
        {footer && <span style={{ marginLeft: "auto" }}>{footer}</span>}
      </div>
    </Card>
  );

  const mailCount = data?.members.filter((m) => m.mail_provider).length ?? 0;
  const tgCount = data?.members.filter((m) => m.telegram).length ?? 0;

  return (
    <div className="st-col">
      <div>
        <div className="eyebrow" style={{ marginBottom: 4 }}>{t("cn.teamTitle")}</div>
        <div style={{ fontSize: 12.5, color: "var(--text-dim)", marginBottom: 10 }}>{t("cn.teamHint")}</div>
        <div className="st-grid-2">
          {card(
            <Icon name="send" size={16} />,
            t("cn.botTitle"),
            t("cn.botDesc"),
            data ? status(data.telegram_bot, t("cn.botOn"), t("cn.botOff")) : <SkeletonLines lines={1} />,
            role === "owner" && data && !data.telegram_bot ? (
              <Link href="/app/settings/tech" className="btn btn-ghost btn-sm">{t("cn.setupInTech")}</Link>
            ) : undefined,
          )}
          {card(
            <span style={{ fontWeight: 800, fontSize: 13 }}>OS</span>,
            "Agency OS",
            t("cn.agencyDesc"),
            <span className="chip" style={{ fontSize: 11.5 }}>{t("cn.soon")}</span>,
          )}
        </div>
      </div>

      <Card>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <div className="eyebrow">{t("cn.peopleTitle")}</div>
          {data && (
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {t("cn.peopleCount", { mail: mailCount, tg: tgCount, n: data.members.length })}
            </span>
          )}
          <Link href="/app/profile" style={{ marginLeft: "auto", fontSize: 12.5, color: "var(--accent)" }}>
            {t("cn.myConnections")} →
          </Link>
        </div>
        <div style={{ fontSize: 12.5, color: "var(--text-dim)", margin: "4px 0 10px" }}>{t("cn.peopleHint")}</div>
        {!data && <SkeletonLines lines={4} />}
        {data && (
          <table className="tbl" style={{ fontSize: 13 }}>
            <thead>
              <tr>
                <th>{t("team.owner.col.member")}</th>
                <th>{t("cn.colMail")}</th>
                <th>{t("cn.colTelegram")}</th>
              </tr>
            </thead>
            <tbody>
              {data.members.map((m) => (
                <tr key={m.user_id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Avatar src={m.avatar_url} initials={m.name.slice(0, 1).toUpperCase()} color={m.color} size={28} />
                      <span style={{ fontWeight: 600 }}>{m.name}</span>
                      <span style={{ color: "var(--text-dim)" }}>· {roleLabel(t, m.role).toLowerCase()}</span>
                    </div>
                  </td>
                  <td>
                    {m.mail_provider ? (
                      <span><span className="st-dot ok" /> {m.mail_address ?? m.mail_provider} <span style={{ color: "var(--text-dim)" }}>· {m.mail_provider === "gmail" ? "Gmail" : "Outlook"}</span></span>
                    ) : (
                      <span style={{ color: "var(--text-dim)" }}><span className="st-dot off" /> {t("cn.notConnected")}</span>
                    )}
                  </td>
                  <td>
                    {m.telegram ? (
                      <span><span className="st-dot ok" /> {t("cn.linked")}</span>
                    ) : (
                      <span style={{ color: "var(--text-dim)" }}><span className="st-dot off" /> {t("cn.notLinked")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
