"use client";

import { hasFullAccess } from "@/lib/roles";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Avatar, Card, SkeletonLines } from "@/components/ui";
import { DeliverabilitySection } from "@/components/settings/DeliverabilitySection";
import { SuppressionsSection } from "@/components/settings/SuppressionsSection";
import {
  getTeamOverview,
  getTelephonyStatus,
  setMemberPhone,
  type OverviewMember,
  type TelephonyStatus,
} from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale } from "@/lib/i18n";
import { roleLabel } from "@/lib/roles";
import { showError, showSuccess } from "@/lib/toast";

/** Связь: как команда звонит и пишет. Телефония — работает ли и с
 * каких номеров звонит каждый; почта — прогрев, лимит, «не писать».
 * Всё техническое (вебхуки провайдера) — во вкладке «Техническое». */
export default function CommsPage() {
  const { t } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [tel, setTel] = useState<TelephonyStatus | null>(null);
  const [people, setPeople] = useState<OverviewMember[] | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!teamId) return;
    getTelephonyStatus(teamId).then(setTel).catch(() => setTel(null));
    getTeamOverview(teamId)
      .then((o) => setPeople(o.members))
      .catch(() => setPeople([]));
  }, [teamId, tick]);

  const savePhone = async (uid: number) => {
    if (!teamId) return;
    try {
      await setMemberPhone(teamId, uid, draft.trim());
      showSuccess(t("tel.saved"));
      setEditing(null);
      setTick((n) => n + 1);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const ok = !!tel?.enabled;
  const providerName = tel?.provider ? tel.provider.charAt(0).toUpperCase() + tel.provider.slice(1) : "";

  return (
    <div className="st-grid-2">
      <Card style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="eyebrow">{t("cm.telTitle")}</div>
          {tel && (
            <span className={"chip" + (ok ? " st-chip-ok" : "")} style={{ marginLeft: "auto", fontSize: 11.5 }}>
              <span className={"st-dot " + (ok ? "ok" : "off")} />
              {ok ? t("cm.telOn", { provider: providerName }) : t("cm.telOff")}
            </span>
          )}
        </div>
        <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.5 }}>
          {ok ? t("cm.telHintOn") : t("cm.telHintOff")}
          {!ok && hasFullAccess(role) && (
            <> <Link href="/app/settings/tech" style={{ color: "var(--accent)" }}>{t("cn.setupInTech")}</Link></>
          )}
        </div>
        {!people && <SkeletonLines lines={4} />}
        {people && (
          <table className="tbl" style={{ fontSize: 13 }}>
            <thead>
              <tr>
                <th>{t("team.owner.col.member")}</th>
                <th>{t("cm.colPhone")}</th>
                <th>{t("cm.colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {people.map((m) => {
                const ext = m.telephony.extension;
                return (
                  <tr key={m.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Avatar src={m.avatar_url} initials={m.initials} color={m.color} size={26} />
                        <span style={{ fontWeight: 600 }}>{m.name}</span>
                        <span style={{ color: "var(--text-dim)" }}>· {roleLabel(t, m.role).toLowerCase()}</span>
                      </div>
                    </td>
                    <td>
                      {editing === m.id ? (
                        <div style={{ display: "flex", gap: 6 }}>
                          <input
                            className="input"
                            value={draft}
                            autoFocus
                            onChange={(e) => setDraft(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && void savePhone(m.id)}
                            placeholder={t("tel.phonePh")}
                            style={{ fontSize: 12, padding: "4px 8px", fontFamily: "var(--font-mono)" }}
                          />
                          <button type="button" className="btn btn-sm" onClick={() => void savePhone(m.id)}>{t("common.save")}</button>
                        </div>
                      ) : ext ? (
                        <button type="button" className="st-link-mono" onClick={() => { setEditing(m.id); setDraft(ext); }} title={ext}>
                          {ext.length > 22 ? `…${ext.slice(ext.lastIndexOf("_"))}` : ext}
                        </button>
                      ) : (
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setEditing(m.id); setDraft(""); }}>
                          {t("cm.setPhone")}
                        </button>
                      )}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {!ext ? (
                        <span style={{ color: "var(--text-dim)" }}>—</span>
                      ) : m.telephony.online === true ? (
                        <span><span className="st-dot ok" /> {t("team.ov.phoneOnline")}</span>
                      ) : m.telephony.online === false ? (
                        <span><span className="st-dot bad" /> {t("team.ov.phoneOffline")}</span>
                      ) : (
                        <span style={{ color: "var(--text-dim)" }}>{t("team.ov.phoneNumber")}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {tel && (
          <div style={{ marginTop: 4 }}>
            <div className="st-row first"><span>{t("cm.recording")}</span><span>{ok ? t("common.on") : t("common.off")}</span></div>
            <div className="st-row"><span>{t("cm.transcription")}</span><span>{tel.transcription ? t("common.on") : t("common.off")}</span></div>
            <div className="st-row"><span>{t("cm.consent")}</span><span>{t("common.on")}</span></div>
          </div>
        )}
      </Card>

      <div className="st-col">
        <DeliverabilitySection />
        <SuppressionsSection />
      </div>
    </div>
  );
}
