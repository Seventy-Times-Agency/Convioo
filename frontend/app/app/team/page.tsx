"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { PipelineEditor } from "@/components/app/PipelineEditor";
import {
  ApiError,
  createInvite,
  createTeam,
  getTeamDetail,
  getTeamMembersSummary,
  listMyTeams,
  updateTeam,
  updateTeamMember,
  type InviteResponse,
  type TeamDetail,
  type TeamMember,
  type TeamMemberSummary,
  type TeamSummary,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import {
  getActiveWorkspace,
  setActiveWorkspace,
  setViewAsMember,
  subscribeWorkspace,
  type Workspace,
} from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

export default function TeamPage() {
  const { t } = useLocale();
  const [workspace, setWorkspace] = useState<Workspace>(() => getActiveWorkspace());
  const [teams, setTeams] = useState<TeamSummary[] | null>(null);
  const [detail, setDetail] = useState<TeamDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => subscribeWorkspace(() => setWorkspace(getActiveWorkspace())), []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    listMyTeams()
      .then((rows) => {
        if (cancelled) return;
        setTeams(rows);
      })
      .catch((e) => {
        if (!cancelled) setError(toMessage(e));
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
      .catch((e) => !cancelled && setError(toMessage(e)));
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

        {teams && teams.length === 0 && (
          <CreateTeamCard
            onCreated={(team) => {
              setActiveWorkspace({
                kind: "team",
                team_id: team.id,
                team_name: team.name,
              });
              refresh();
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
              }}
            />
          </>
        )}

        {detail && <TeamDetailBlock detail={detail} onRefresh={refresh} />}
      </div>
    </>
  );
}

function CreateTeamCard({ onCreated }: { onCreated: (team: TeamDetail) => void }) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setErr(null);
    try {
      const team = await createTeam(name.trim());
      onCreated(team);
    } catch (ex) {
      setErr(toMessage(ex));
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
      {err && (
        <div style={{ marginTop: 12, fontSize: 13, color: "var(--cold)" }}>{err}</div>
      )}
    </div>
  );
}

function CreateTeamInline({ onCreated }: { onCreated: (team: TeamDetail) => void }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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
    setErr(null);
    try {
      const team = await createTeam(name.trim());
      onCreated(team);
      setOpen(false);
      setName("");
    } catch (ex) {
      setErr(toMessage(ex));
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
          setErr(null);
        }}
      >
        {t("common.cancel")}
      </button>
      {err && (
        <div style={{ fontSize: 13, color: "var(--cold)", marginLeft: 12 }}>{err}</div>
      )}
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
            · {team.role}
          </span>
        </button>
      ))}
    </div>
  );
}

function TeamDetailBlock({
  detail,
  onRefresh,
}: {
  detail: TeamDetail;
  onRefresh: () => void;
}) {
  const { t } = useLocale();
  const isOwner = detail.role === "owner";

  return (
    <>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
          }}
        >
          <div>
            <div className="eyebrow" style={{ marginBottom: 4 }}>
              {t("team.detail.eyebrow")}
            </div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{detail.name}</div>
          </div>
          <div className="chip">{detail.role}</div>
        </div>

        <TeamDescriptionBlock
          teamId={detail.id}
          isOwner={isOwner}
          description={detail.description}
          onSaved={onRefresh}
        />

        <div className="eyebrow" style={{ marginTop: 18, marginBottom: 10 }}>
          {t("team.detail.members", { n: detail.members.length })}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {detail.members.map((m) => (
            <MemberRow
              key={m.id}
              teamId={detail.id}
              member={m}
              isOwner={isOwner}
              onSaved={onRefresh}
            />
          ))}
        </div>
      </div>

      <PipelineEditor teamId={detail.id} />

      {isOwner && <OwnerMembersBlock teamId={detail.id} />}
      {isOwner && <InviteBlock teamId={detail.id} />}
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
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setDraft(description ?? "");
  }, [description]);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await updateTeam(teamId, { description: draft.trim() || null });
      setEditing(false);
      onSaved();
    } catch (e) {
      setErr(toMessage(e));
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
        <div
          style={{
            fontSize: 13.5,
            color: description ? "var(--text)" : "var(--text-dim)",
            lineHeight: 1.55,
          }}
        >
          {description || t("team.descriptionEmpty")}
        </div>
      )}

      {editing && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <textarea
            className="textarea"
            rows={3}
            value={draft}
            maxLength={500}
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
                setErr(null);
              }}
            >
              {t("common.cancel")}
            </button>
            {err && (
              <div style={{ fontSize: 12, color: "var(--cold)", alignSelf: "center" }}>
                {err}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MemberRow({
  teamId,
  member,
  isOwner,
  onSaved,
}: {
  teamId: string;
  member: TeamMember;
  isOwner: boolean;
  onSaved: () => void;
}) {
  const { t } = useLocale();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(member.description ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      await updateTeamMember(teamId, member.id, {
        description: draft.trim() || null,
      });
      setEditing(false);
      onSaved();
    } catch (e) {
      setErr(toMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        padding: "10px 12px",
        background: "var(--surface-2)",
        borderRadius: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div className="avatar" style={{ background: member.color }}>
          {member.initials}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{member.name}</div>
          {!editing && member.description && (
            <div
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                marginTop: 2,
                lineHeight: 1.45,
              }}
            >
              {member.description}
            </div>
          )}
          {!editing && !member.description && isOwner && (
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
              {t("team.member.descriptionEmpty")}
            </div>
          )}
        </div>
        <span className="chip" style={{ fontSize: 11 }}>
          {member.role}
        </span>
        {isOwner && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="btn-icon"
            title={t("common.edit")}
          >
            <Icon name="pencil" size={13} />
          </button>
        )}
      </div>
      {editing && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <textarea
            className="textarea"
            rows={2}
            value={draft}
            maxLength={300}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("team.member.descriptionPh")}
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
                setDraft(member.description ?? "");
                setEditing(false);
                setErr(null);
              }}
            >
              {t("common.cancel")}
            </button>
            {err && (
              <div style={{ fontSize: 12, color: "var(--cold)", alignSelf: "center" }}>
                {err}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function OwnerMembersBlock({ teamId }: { teamId: string }) {
  const { t } = useLocale();
  const router = useRouter();
  const [rows, setRows] = useState<TeamMemberSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const me = getCurrentUser();

  useEffect(() => {
    let cancelled = false;
    getTeamMembersSummary(teamId)
      .then((r) => !cancelled && setRows(r))
      .catch((e) => !cancelled && setErr(toMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const viewAs = (member: TeamMemberSummary) => {
    if (me && member.user_id === me.user_id) {
      setViewAsMember(undefined);
    } else {
      setViewAsMember(member.user_id, member.name);
    }
    router.push("/app");
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {t("team.owner.eyebrow")}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
        {t("team.owner.title")}
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 16,
        }}
      >
        {t("team.owner.subtitle")}
      </div>

      {err && (
        <div style={{ fontSize: 13, color: "var(--cold)", marginBottom: 12 }}>
          {err}
        </div>
      )}
      {!rows && !err && (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("common.loading")}
        </div>
      )}
      {rows && rows.length === 0 && (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("team.owner.empty")}
        </div>
      )}
      {rows && rows.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th>{t("team.owner.col.member")}</th>
              <th>{t("team.owner.col.role")}</th>
              <th>{t("team.owner.col.sessions")}</th>
              <th>{t("team.owner.col.leads")}</th>
              <th>{t("team.owner.col.hot")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.user_id}>
                <td>
                  <div style={{ fontWeight: 600 }}>{row.name}</div>
                </td>
                <td>
                  <span className="chip" style={{ fontSize: 11 }}>
                    {row.role}
                  </span>
                </td>
                <td>{row.sessions_total}</td>
                <td>{row.leads_total}</td>
                <td style={{ color: "var(--hot)", fontWeight: 600 }}>
                  {row.hot_total}
                </td>
                <td>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => viewAs(row)}
                  >
                    {me && row.user_id === me.user_id
                      ? t("team.owner.viewMine")
                      : t("team.owner.viewAs")}{" "}
                    <Icon name="arrow" size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function InviteBlock({ teamId }: { teamId: string }) {
  const { t } = useLocale();
  const [invite, setInvite] = useState<InviteResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!invite) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [invite]);

  const inviteUrl = useMemo(() => {
    if (!invite) return "";
    if (typeof window === "undefined") return `/join/${invite.token}`;
    return `${window.location.origin}/join/${invite.token}`;
  }, [invite]);

  const generate = async () => {
    setSubmitting(true);
    setErr(null);
    try {
      const r = await createInvite(teamId, { ttlSeconds: 600 });
      setInvite(r);
    } catch (e) {
      setErr(toMessage(e));
    } finally {
      setSubmitting(false);
    }
  };

  const copy = () => {
    if (!inviteUrl) return;
    navigator.clipboard?.writeText(inviteUrl);
  };

  const remaining = invite
    ? Math.max(0, Math.floor((new Date(invite.expires_at).getTime() - now) / 1000))
    : 0;
  const expired = invite !== null && remaining <= 0;

  return (
    <div className="card" style={{ padding: 24 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        {t("team.invite.eyebrow")}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
        {t("team.invite.title")}
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 16,
        }}
      >
        {t("team.invite.subtitle")}
      </div>

      {!invite && (
        <button
          type="button"
          className="btn"
          onClick={generate}
          disabled={submitting}
        >
          {submitting ? t("common.loading") : t("team.invite.generate")}
        </button>
      )}

      {invite && (
        <div>
          <div
            style={{
              display: "flex",
              gap: 8,
              alignItems: "stretch",
              marginBottom: 10,
            }}
          >
            <input
              className="input"
              value={inviteUrl}
              readOnly
              style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: 12 }}
              onFocus={(e) => e.currentTarget.select()}
            />
            <button type="button" className="btn" onClick={copy}>
              {t("team.invite.copy")}
            </button>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              fontSize: 12,
              color: expired ? "var(--cold)" : "var(--text-muted)",
            }}
          >
            <Icon name="clock" size={12} />
            {expired
              ? t("team.invite.expired")
              : t("team.invite.expiresIn", { mm: formatRemaining(remaining) })}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={generate}
              disabled={submitting}
              style={{ marginLeft: "auto" }}
            >
              {t("team.invite.regenerate")}
            </button>
          </div>
        </div>
      )}

      {err && (
        <div style={{ marginTop: 12, fontSize: 13, color: "var(--cold)" }}>{err}</div>
      )}
    </div>
  );
}

function formatRemaining(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function toMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
