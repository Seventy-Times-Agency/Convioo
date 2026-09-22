"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui";
import {
  createSquad,
  deleteSquad,
  listSquads,
  setMemberSquad,
  updateSquad,
  type Squad,
  type TeamMember,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

/**
 * Команды внутри компании. Управляют РОП и владелец: создать,
 * назначить тимлида, раздать людей, распустить. Тимлид после этого
 * видит только свою команду (+ свободный пул), сводка со всех
 * команд уходит наверх.
 */
export function SquadsCard({
  teamId,
  members,
  canManage,
  onChanged,
}: {
  teamId: string;
  members: TeamMember[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const [squads, setSquads] = useState<Squad[] | null>(null);
  const [newName, setNewName] = useState("");
  const [newLead, setNewLead] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    listSquads(teamId)
      .then((d) => setSquads(d.squads))
      .catch(() => setSquads([]));
  }, [teamId]);

  useEffect(reload, [reload]);

  const create = async () => {
    if (!newName.trim() || busy) return;
    setBusy(true);
    try {
      await createSquad(teamId, {
        name: newName.trim(),
        lead_user_id: newLead ? Number(newLead) : null,
      });
      setNewName("");
      setNewLead("");
      reload();
      onChanged();
      showSuccess(t("squads.created"));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (sq: Squad) => {
    const ok = await confirmAsync(
      t("squads.deleteConfirm", { name: sq.name }),
    );
    if (!ok) return;
    try {
      await deleteSquad(sq.id);
      reload();
      onChanged();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const move = async (memberId: number, squadId: string) => {
    try {
      await setMemberSquad(teamId, memberId, squadId);
      reload();
      onChanged();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const setLead = async (sq: Squad, userId: string) => {
    try {
      await updateSquad(sq.id, {
        lead_user_id: userId ? Number(userId) : null,
      });
      reload();
      onChanged();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  if (squads === null) return null;
  if (squads.length === 0 && !canManage) return null;

  const managers = members.filter(
    (m) => m.role === "manager" || m.role === "admin" || m.role === "owner",
  );

  return (
    <div className="card" style={{ padding: 20, marginBottom: 14 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 6,
        }}
      >
        <span className="eyebrow">{t("squads.title")}</span>
        <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
          {t("squads.hint")}
        </span>
      </div>

      {squads.length === 0 && (
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-dim)",
            lineHeight: 1.5,
            margin: "6px 0 10px",
          }}
        >
          {t("squads.empty")}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {squads.map((sq) => {
          const inSquad = members.filter((m) => m.squad_id === sq.id);
          const free = members.filter((m) => !m.squad_id);
          return (
            <div
              key={sq.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 11,
                padding: "12px 14px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontWeight: 800, fontSize: 14 }}>
                  {sq.name}
                </span>
                <span
                  style={{ fontSize: 12, color: "var(--text-dim)" }}
                >
                  {t("squads.membersCount", { n: inSquad.length })}
                </span>
                {canManage ? (
                  <select
                    className="input"
                    value={sq.lead_user_id ?? ""}
                    onChange={(e) => void setLead(sq, e.target.value)}
                    style={{
                      width: "auto",
                      fontSize: 12,
                      padding: "4px 8px",
                      marginLeft: "auto",
                    }}
                  >
                    <option value="">{t("squads.noLead")}</option>
                    {managers.map((m) => (
                      <option key={m.id} value={m.id}>
                        {t("squads.leadPrefix")} {m.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  sq.lead_name && (
                    <span
                      style={{
                        marginLeft: "auto",
                        fontSize: 12,
                        color: "var(--text-muted)",
                      }}
                    >
                      {t("squads.leadPrefix")} {sq.lead_name}
                    </span>
                  )
                )}
                {canManage && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void remove(sq)}
                    aria-label={t("common.delete")}
                  >
                    <Icon name="x" size={13} />
                  </button>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  gap: 6,
                  flexWrap: "wrap",
                  marginTop: 8,
                  alignItems: "center",
                }}
              >
                {inSquad.map((m) => (
                  <span
                    key={m.id}
                    className="chip"
                    style={{ fontSize: 11.5, gap: 6 }}
                  >
                    {m.name}
                    {canManage && (
                      <button
                        type="button"
                        onClick={() => void move(m.id, "")}
                        title={t("squads.toPool")}
                        style={{
                          border: "none",
                          background: "none",
                          cursor: "pointer",
                          color: "var(--text-dim)",
                          padding: 0,
                          lineHeight: 1,
                        }}
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
                {canManage && free.length > 0 && (
                  <select
                    className="input"
                    value=""
                    onChange={(e) => {
                      if (e.target.value)
                        void move(Number(e.target.value), sq.id);
                    }}
                    style={{
                      width: "auto",
                      fontSize: 11.5,
                      padding: "3px 8px",
                    }}
                  >
                    <option value="">{t("squads.addMember")}</option>
                    {free.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {canManage && (
        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 12,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <input
            className="input"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t("squads.namePh")}
            style={{ width: 200, fontSize: 13 }}
          />
          <select
            className="input"
            value={newLead}
            onChange={(e) => setNewLead(e.target.value)}
            style={{ width: "auto", fontSize: 12.5 }}
          >
            <option value="">{t("squads.noLead")}</option>
            {managers.map((m) => (
              <option key={m.id} value={m.id}>
                {t("squads.leadPrefix")} {m.name}
              </option>
            ))}
          </select>
          <Button size="sm" onClick={() => void create()} disabled={busy || !newName.trim()}>
            <Icon name="plus" size={13} />
            {t("squads.create")}
          </Button>
        </div>
      )}
    </div>
  );
}
