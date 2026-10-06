"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/brand/Icon";
import {
  ApiError,
  createTeam,
  getTeamDetail,
  listMyTeams,
  updateTeam,
  type TeamDetail,
  type TeamSummary,
} from "@/lib/api";
import {
  getActiveWorkspace,
  setActiveWorkspace,
  subscribeWorkspace,
  type Workspace,
} from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { SquadsCard } from "@/components/team/SquadsCard";
import { TeamOverview } from "@/components/team/TeamOverview";
import { roleLabel } from "@/lib/roles";

export default function TeamPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [workspace, setWorkspace] = useState<Workspace>(() => getActiveWorkspace());
  const [teams, setTeams] = useState<TeamSummary[] | null>(null);
  const [detail, setDetail] = useState<TeamDetail | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => subscribeWorkspace(() => setWorkspace(getActiveWorkspace())), []);

  useEffect(() => {
    let cancelled = false;
    listMyTeams()
      .then((rows) => {
        if (cancelled) return;
        setTeams(rows);
      })
      .catch((e) => {
        if (!cancelled) showError(toMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const activeTeamId = workspace.kind === "team" ? workspace.team_id : null;
  const focusedTeamId =
    activeTeamId ?? (teams && teams.length > 0 ? teams[0].id : null);

  useEffect(() => {
    if (!focusedTeamId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    getTeamDetail(focusedTeamId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && showError(toMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [focusedTeamId, refreshKey]);

  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <>
      <Topbar
        title={t("team.title")}
        subtitle={t("team.subtitle")}
      />
      <div className="page" style={{ maxWidth: 1040 }}>
        {teams && teams.length === 0 && (
          <CreateTeamCard
            onCreated={(team) => {
              setActiveWorkspace({
                kind: "team",
                team_id: team.id,
                team_name: team.name,
              });
              refresh();
              // Продукт рождается пустым: сразу после создания команды —
              // мастер первой воронки (цель, путь касаний, скрипт).
              router.push("/app/funnels?new=1");
            }}
          />
        )}

        {teams && teams.length > 0 && (
          <>
            <TeamSwitcher
              teams={teams}
              focusedTeamId={focusedTeamId}
              onSelect={(team) => {
                setActiveWorkspace({
                  kind: "team",
                  team_id: team.id,
                  team_name: team.name,
                });
              }}
            />
            <CreateTeamInline
              onCreated={(team) => {
                setActiveWorkspace({
                  kind: "team",
                  team_id: team.id,
                  team_name: team.name,
                });
                refresh();
                router.push("/app/funnels?new=1");
              }}
            />
          </>
        )}

        {detail && (
          <TeamDetailBlock detail={detail} onRefresh={refresh} refreshKey={refreshKey} />
        )}
      </div>
    </>
  );
}

function CreateTeamCard({ onCreated }: { onCreated: (team: TeamDetail) => void }) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const team = await createTeam(name.trim());
      onCreated(team);
    } catch (ex) {
      showError(toMessage(ex));
      setSubmitting(false);
    }
  };

  return (
    <div className="card" style={{ padding: 28, marginBottom: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {t("team.create.eyebrow")}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>
        {t("team.create.title")}
      </div>
      <div
        style={{
          fontSize: 14,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 20,
        }}
      >
        {t("team.create.subtitle")}
      </div>
      <form onSubmit={submit} style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          placeholder={t("team.create.placeholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ flex: 1 }}
        />
        <button
          type="submit"
          className="btn"
          disabled={submitting || !name.trim()}
        >
          {submitting ? t("common.loading") : t("team.create.submit")}{" "}
          <Icon name="arrow" size={14} />
        </button>
      </form>
    </div>
  );
}

function CreateTeamInline({ onCreated }: { onCreated: (team: TeamDetail) => void }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => setOpen(true)}
        style={{ marginBottom: 16 }}
      >
        <Icon name="plus" size={14} /> {t("team.create.another")}
      </button>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const team = await createTeam(name.trim());
      onCreated(team);
      setOpen(false);
      setName("");
    } catch (ex) {
      showError(toMessage(ex));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      <input
        className="input"
        placeholder={t("team.create.placeholder")}
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
        style={{ flex: 1 }}
      />
      <button type="submit" className="btn" disabled={submitting || !name.trim()}>
        {submitting ? t("common.loading") : t("team.create.submit")}
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => {
          setOpen(false);
        }}
      >
        {t("common.cancel")}
      </button>
    </form>
  );
}

function TeamSwitcher({
  teams,
  focusedTeamId,
  onSelect,
}: {
  teams: TeamSummary[];
  focusedTeamId: string | null;
  onSelect: (team: TeamSummary) => void;
}) {
  const { t } = useLocale();
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        marginBottom: 16,
      }}
    >
      {teams.map((team) => (
        <button
          key={team.id}
          type="button"
          className="chip"
          onClick={() => onSelect(team)}
          style={{
            padding: "8px 14px",
            fontSize: 13,
            cursor: "pointer",
            border:
              team.id === focusedTeamId
                ? "1px solid var(--accent)"
                : "1px solid var(--border)",
            background:
              team.id === focusedTeamId
                ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                : "var(--surface)",
            color:
              team.id === focusedTeamId ? "var(--accent)" : "var(--text)",
          }}
        >
          {team.name}{" "}
          <span style={{ color: "var(--text-dim)", marginLeft: 6, fontSize: 11 }}>
            · {roleLabel(t, team.role)}
          </span>
        </button>
      ))}
    </div>
  );
}

function TeamDetailBlock({
  detail,
  onRefresh,
  refreshKey,
}: {
  detail: TeamDetail;
  onRefresh: () => void;
  refreshKey: number;
}) {
  const { t } = useLocale();
  const isOwner = detail.role === "owner";
  // Owner и РОП управляют составом; тимлид видит панель только по
  // своим селзам (фильтрует сервер); селзу панель не показываем.
  const canManageMembers = detail.role === "owner" || detail.role === "admin";
  if (detail.role === "sales") {
    return (
      <div className="card" style={{ padding: 24 }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{detail.name}</div>
        <div style={{ fontSize: 13.5, color: "var(--text-muted)", marginTop: 6 }}>
          {t("team.ov.salesNoPanel")}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="card" style={{ padding: "18px 20px", marginBottom: 12 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div className="eyebrow" style={{ marginBottom: 2 }}>
              {t("team.detail.eyebrow")}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{detail.name}</div>
          </div>
          <div className="chip">{roleLabel(t, detail.role)}</div>
        </div>

        <TeamDescriptionBlock
          teamId={detail.id}
          isOwner={isOwner}
          description={detail.description}
          onSaved={onRefresh}
        />
      </div>

      <TeamOverview teamId={detail.id} onChanged={onRefresh} refreshKey={refreshKey} />

      {canManageMembers && (
        <SquadsCard
          teamId={detail.id}
          members={detail.members}
          canManage={canManageMembers}
          onChanged={onRefresh}
        />
      )}
    </>
  );
}

function TeamDescriptionBlock({
  teamId,
  isOwner,
  description,
  onSaved,
}: {
  teamId: string;
  isOwner: boolean;
  description: string | null;
  onSaved: () => void;
}) {
  const { t } = useLocale();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(description ?? "");
  const [saving, setSaving] = useState(false);
  // Справка о компании длинная; по умолчанию показываем три строки,
  // остальное — по клику, чтобы не занимать весь экран.
  const [expanded, setExpanded] = useState(false);
  const isLong = (description ?? "").length > 320;

  useEffect(() => {
    setDraft(description ?? "");
  }, [description]);

  const save = async () => {
    setSaving(true);
    try {
      await updateTeam(teamId, { description: draft.trim() || null });
      setEditing(false);
      onSaved();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ marginTop: 8 }}>
      <div
        className="eyebrow"
        style={{
          marginBottom: 6,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span>{t("team.descriptionLabel")}</span>
        {isOwner && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              color: "var(--accent)",
              fontSize: 11,
            }}
          >
            <Icon name="pencil" size={11} /> {t("common.edit")}
          </button>
        )}
      </div>

      {!editing && (
        <>
          <div
            style={{
              fontSize: 13.5,
              color: description ? "var(--text)" : "var(--text-dim)",
              lineHeight: 1.55,
              whiteSpace: "pre-line",
              ...(isLong && !expanded
                ? {
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical" as const,
                    overflow: "hidden",
                  }
                : {}),
            }}
          >
            {description || t("team.descriptionEmpty")}
          </div>
          {isLong && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ alignSelf: "flex-start", marginTop: 4 }}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? t("team.descriptionLess") : t("team.descriptionMore")}
            </button>
          )}
        </>
      )}

      {editing && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <textarea
            className="textarea"
            rows={3}
            value={draft}
            maxLength={4000}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("team.descriptionPh")}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={saving}
              onClick={save}
            >
              {saving ? t("common.loading") : t("common.save")}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setDraft(description ?? "");
                setEditing(false);
              }}
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function toMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}


