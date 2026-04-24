"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { type TeamMember, getTeam } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

export default function TeamPage() {
  const { t } = useLocale();
  const [members, setMembers] = useState<TeamMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getTeam()
      .then(setMembers)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <>
      <Topbar
        title={t("team.title")}
        subtitle={t("team.subtitle")}
        right={
          <button className="btn btn-sm" type="button" disabled>
            <Icon name="plus" size={14} /> {t("common.invite")}
          </button>
        }
      />
      <div className="page" style={{ maxWidth: 900 }}>
        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              color: "var(--cold)",
              borderColor: "var(--cold)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}
        {members && members.length === 0 && !error && (
          <div
            className="card"
            style={{
              padding: 32,
              textAlign: "center",
              color: "var(--text-muted)",
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text)" }}>
              {t("team.empty.title")}
            </div>
            <div style={{ fontSize: 13, marginTop: 6 }}>
              {t("team.empty.body")}
            </div>
          </div>
        )}
        {members && members.length > 0 && (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>{t("team.table.member")}</th>
                  <th>{t("team.table.role")}</th>
                  <th>{t("team.table.active")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div className="avatar" style={{ background: m.color }}>
                          {m.initials}
                        </div>
                        <div>
                          <div style={{ fontWeight: 600 }}>{m.name}</div>
                          {m.email && (
                            <div
                              style={{
                                fontSize: 11.5,
                                color: "var(--text-muted)",
                              }}
                            >
                              {m.email}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="chip" style={{ fontSize: 11 }}>
                        {m.role}
                      </span>
                    </td>
                    <td style={{ color: "var(--text-muted)", fontSize: 12.5 }}>
                      {m.last_active ?? t("common.none")}
                    </td>
                    <td>
                      <button className="btn-icon" type="button">
                        <Icon name="moreH" size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
