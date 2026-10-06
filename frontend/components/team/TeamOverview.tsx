"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/brand/Icon";
import { Avatar, CountUp } from "@/components/ui";
import {
  ApiError,
  createInvite,
  getTeamOverview,
  removeTeamMember,
  setMemberPhone,
  setMemberTargets,
  transferOwnership,
  updateTeamMember,
  type InviteResponse,
  type OverviewMember,
  type TeamOverview as TeamOverviewData,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { setViewAsMember } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { roleLabel } from "@/lib/roles";

/**
 * Панель управления командой. Одна таблица на всех, кого видит
 * вызывающий (сервер уже отфильтровал по роли): лиды, звонки против
 * плана, телефония, действия. Что можно делать с каждой строкой —
 * тоже решает сервер (can_*), здесь только рисуем.
 */
export function TeamOverview({
  teamId,
  onChanged,
  refreshKey,
}: {
  teamId: string;
  onChanged: () => void;
  refreshKey: number;
}) {
  const { t } = useLocale();
  const [data, setData] = useState<TeamOverviewData | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getTeamOverview(teamId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && showError(toMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [teamId, refreshKey, tick]);

  const reload = () => {
    setTick((k) => k + 1);
    onChanged();
  };

  if (!data) {
    return (
      <div className="card" style={{ padding: 20, fontSize: 13, color: "var(--text-muted)" }}>
        {t("common.loading")}
      </div>
    );
  }

  const canInvite = data.role === "owner" || data.role === "admin";
  const roleOrder = ["owner", "admin", "manager", "sales"];
  const peopleLine = roleOrder
    .filter((r) => data.people_by_role[r])
    .map((r) => `${data.people_by_role[r]} ${roleLabel(t, r).toLowerCase()}`)
    .join(" · ");
  const planCalls = data.members.reduce((n, m) => n + (m.target_calls_day ?? 0), 0);
  const planGoals = data.members.reduce((n, m) => n + (m.target_goals_week ?? 0), 0);

  return (
    <div className="card" style={{ padding: 0, marginBottom: 16, overflow: "hidden" }}>
      {/* Показатели отдела */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <Stat
          label={t("team.stat.people")}
          value={data.people}
          hint={peopleLine}
        />
        <Stat
          label={t("team.stat.leads")}
          value={data.leads_in_work}
          hint={t("team.ov.freePool", { n: data.free_pool })}
        />
        <Stat
          label={t("team.ov.callsToday")}
          value={planCalls ? `${data.calls_today} / ${planCalls}` : data.calls_today}
          hint={t("team.ov.talksHint", { n: data.talks_today })}
          tone={planCalls ? progressTone(data.calls_today, planCalls) : undefined}
        />
        <Stat
          label={t("team.ov.goalsWeek")}
          value={planGoals ? `${data.goals_7d} / ${planGoals}` : data.goals_7d}
          hint={t("team.ov.goalsHint")}
          tone={planGoals ? progressTone(data.goals_7d, planGoals) : undefined}
        />
        {canInvite && (
          <InviteCell teamId={teamId} pending={data.pending_invites} />
        )}
      </div>

      {/* Таблица людей */}
      <div style={{ overflowX: "auto" }}>
        <table className="tbl team-ov-tbl" style={{ fontSize: 13 }}>
          <thead>
            <tr>
              <th>{t("team.owner.col.member")}</th>
              <th>{t("team.owner.col.role")}</th>
              <th style={{ textAlign: "right" }}>{t("team.owner.col.leads")}</th>
              <th>{t("team.ov.col.today")}</th>
              <th>{t("team.ov.col.week")}</th>
              <th>{t("team.ov.col.phone")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.members.map((m) => (
              <MemberLine
                key={m.id}
                teamId={teamId}
                member={m}
                all={data.members}
                callerRole={data.role}
                onChanged={reload}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function progressTone(done: number, plan: number): "ok" | "warn" | "bad" {
  if (plan <= 0) return "ok";
  const r = done / plan;
  if (r >= 1) return "ok";
  if (r >= 0.5) return "warn";
  return "bad";
}

const TONE_COLOR: Record<"ok" | "warn" | "bad", string> = {
  ok: "var(--accent)",
  warn: "var(--warm, #c98a1b)",
  bad: "var(--cold)",
};

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <div
      style={{
        padding: "14px 16px",
        borderRight: "1px solid var(--border)",
        minWidth: 0,
      }}
    >
      <div
        style={{
          fontSize: 9.5,
          fontWeight: 800,
          letterSpacing: "0.09em",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 24,
          fontWeight: 800,
          lineHeight: 1.15,
          marginTop: 4,
          fontVariantNumeric: "tabular-nums",
          color: tone ? TONE_COLOR[tone] : "var(--text)",
        }}
      >
        {typeof value === "number" ? <CountUp value={value} /> : value}
      </div>
      {hint && (
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 2,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={hint}
        >
          {hint}
        </div>
      )}
    </div>
  );
}

/** Компактный инвайт: кнопка в полосе показателей, ссылка — под ней. */
function InviteCell({ teamId, pending }: { teamId: string; pending: number }) {
  const { t } = useLocale();
  const [invite, setInvite] = useState<InviteResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const url = useMemo(() => {
    if (!invite) return "";
    if (typeof window === "undefined") return `/join/${invite.token}`;
    return `${window.location.origin}/join/${invite.token}`;
  }, [invite]);

  const generate = async () => {
    setBusy(true);
    try {
      const r = await createInvite(teamId, { ttlSeconds: 600 });
      setInvite(r);
      setCopied(false);
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const copy = () => {
    if (!url) return;
    navigator.clipboard?.writeText(url);
    setCopied(true);
  };

  return (
    <div style={{ padding: "14px 16px", minWidth: 0 }}>
      <div
        style={{
          fontSize: 9.5,
          fontWeight: 800,
          letterSpacing: "0.09em",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        {t("team.stat.invites")}
      </div>
      {!invite ? (
        <button
          type="button"
          className="btn btn-sm"
          style={{ marginTop: 8 }}
          onClick={generate}
          disabled={busy}
        >
          <Icon name="plus" size={12} /> {t("team.ov.invite")}
        </button>
      ) : (
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <button type="button" className="btn btn-sm" onClick={copy}>
            <Icon name={copied ? "check" : "copy"} size={12} />{" "}
            {copied ? t("team.ov.copied") : t("team.invite.copy")}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={generate}
            disabled={busy}
            title={t("team.invite.regenerate")}
          >
            <Icon name="rotateCcw" size={12} />
          </button>
        </div>
      )}
      <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 4 }}>
        {invite
          ? t("team.ov.inviteTtl")
          : t("team.ov.pendingInvites", { n: pending })}
      </div>
    </div>
  );
}

function Progress({
  done,
  plan,
  label,
}: {
  done: number;
  plan: number | null;
  label?: string;
}) {
  if (!plan) {
    return (
      <span style={{ fontVariantNumeric: "tabular-nums" }}>
        {done}
        {label && (
          <span style={{ color: "var(--text-dim)", fontSize: 11.5 }}> {label}</span>
        )}
      </span>
    );
  }
  const tone = progressTone(done, plan);
  const pct = Math.min(100, Math.round((done / plan) * 100));
  return (
    <div style={{ minWidth: 92 }}>
      <div style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
        {done}
        <span style={{ color: "var(--text-dim)", fontWeight: 400 }}> / {plan}</span>
        {label && (
          <span style={{ color: "var(--text-dim)", fontSize: 11.5, fontWeight: 400 }}>
            {" "}
            {label}
          </span>
        )}
      </div>
      <div
        style={{
          height: 4,
          borderRadius: 2,
          background: "var(--surface-2)",
          marginTop: 4,
          overflow: "hidden",
        }}
      >
        <div
          className="m-bar"
          style={{
            width: `${pct}%`,
            height: "100%",
            background: TONE_COLOR[tone],
          }}
        />
      </div>
    </div>
  );
}

function TelephonyCell({ m }: { m: OverviewMember }) {
  const { t } = useLocale();
  const ext = m.telephony.extension;
  if (!ext) {
    return (
      <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
        <Dot color="var(--border)" /> {t("team.ov.phoneNone")}
      </span>
    );
  }
  const online = m.telephony.online;
  const color =
    online === true ? "var(--accent)" : online === false ? "var(--cold)" : "var(--text-dim)";
  const isSip = !/^[+\d\s()-]+$/.test(ext);
  const text =
    online === true
      ? t("team.ov.phoneOnline")
      : online === false
        ? t("team.ov.phoneOffline")
        : isSip
          ? "SIP"
          : t("team.ov.phoneNumber");
  return (
    <span style={{ fontSize: 12, whiteSpace: "nowrap" }} title={ext}>
      <Dot color={color} /> {text}
      <span style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
        {" "}
        {shortExt(ext)}
      </span>
    </span>
  );
}

function Dot({ color }: { color: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        verticalAlign: "middle",
        marginRight: 2,
      }}
    />
  );
}

function shortExt(ext: string): string {
  // SIP-логины у Ringostat длинные: project_login — показываем хвост.
  const i = ext.lastIndexOf("_");
  if (i > 0 && ext.length > 18) return "…" + ext.slice(i);
  return ext;
}

function MemberLine({
  teamId,
  member: m,
  all,
  callerRole,
  onChanged,
}: {
  teamId: string;
  member: OverviewMember;
  all: OverviewMember[];
  callerRole: string;
  onChanged: () => void;
}) {
  const { t } = useLocale();
  const router = useRouter();
  const me = getCurrentUser();
  const isSelf = me?.user_id === m.id;
  const [panel, setPanel] = useState<"none" | "edit" | "targets" | "transfer">("none");
  const [busy, setBusy] = useState(false);

  // edit
  const [desc, setDesc] = useState(m.description ?? "");
  const [ext, setExt] = useState(m.telephony.extension ?? "");
  // targets
  const [tCalls, setTCalls] = useState(m.target_calls_day?.toString() ?? "");
  const [tGoals, setTGoals] = useState(m.target_goals_week?.toString() ?? "");
  // transfer-on-remove
  const [transferPick, setTransferPick] = useState<number | "">("");

  useEffect(() => {
    setDesc(m.description ?? "");
    setExt(m.telephony.extension ?? "");
    setTCalls(m.target_calls_day?.toString() ?? "");
    setTGoals(m.target_goals_week?.toString() ?? "");
  }, [m]);

  const roleOptions =
    callerRole === "owner" ? ["owner", "admin", "manager", "sales"] : ["manager", "sales"];

  const changeRole = async (next: string) => {
    if (next === m.role) return;
    setBusy(true);
    try {
      if (next === "owner") {
        const ok = await confirmAsync(t("team.member.confirmTransferOwner"));
        if (!ok) return;
        await transferOwnership(teamId, m.id);
      } else {
        await updateTeamMember(teamId, m.id, { role: next });
      }
      onChanged();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    setBusy(true);
    try {
      if ((m.description ?? "") !== desc.trim()) {
        await updateTeamMember(teamId, m.id, { description: desc.trim() || null });
      }
      if ((m.telephony.extension ?? "") !== ext.trim()) {
        await setMemberPhone(teamId, m.id, ext.trim());
      }
      setPanel("none");
      onChanged();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const saveTargets = async () => {
    setBusy(true);
    try {
      await setMemberTargets(teamId, m.id, {
        target_calls_day: tCalls === "" ? null : Number(tCalls),
        target_goals_week: tGoals === "" ? null : Number(tGoals),
      });
      setPanel("none");
      onChanged();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const doRemove = async (transferTo?: number) => {
    setBusy(true);
    try {
      await removeTeamMember(teamId, m.id, transferTo);
      setPanel("none");
      onChanged();
    } catch (e) {
      // 409 — за участником лиды, сервер требует передать их.
      if (e instanceof ApiError && e.status === 409) {
        setPanel("transfer");
      } else {
        showError(toMessage(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const startRemove = async () => {
    const ok = await confirmAsync(t("team.member.confirmRemove"));
    if (!ok) return;
    await doRemove();
  };

  const viewAs = () => {
    if (isSelf) setViewAsMember(undefined);
    else setViewAsMember(m.id, m.name);
    router.push("/app");
  };

  const toggle = (p: typeof panel) => setPanel((cur) => (cur === p ? "none" : p));

  return (
    <>
      <tr>
        <td style={{ minWidth: 170 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Avatar src={m.avatar_url} initials={m.initials} color={m.color} size={30} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                {m.name}
                {isSelf && (
                  <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: 11.5 }}>
                    {" "}
                    · {t("team.ov.you")}
                  </span>
                )}
              </div>
              {m.description && (
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--text-muted)",
                    maxWidth: 220,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={m.description}
                >
                  {m.description}
                </div>
              )}
            </div>
          </div>
        </td>
        <td>
          {m.can_change_role ? (
            <select
              className="select"
              value={m.role}
              disabled={busy}
              onChange={(e) => changeRole(e.target.value)}
              style={{ fontSize: 12, padding: "3px 6px", width: "auto", flex: "none" }}
              title={t("team.member.changeRole")}
            >
              {(roleOptions.includes(m.role) ? roleOptions : [m.role, ...roleOptions]).map(
                (r) => (
                  <option key={r} value={r}>
                    {roleLabel(t, r)}
                  </option>
                ),
              )}
            </select>
          ) : (
            <span className="chip" style={{ fontSize: 11 }}>
              {roleLabel(t, m.role)}
            </span>
          )}
        </td>
        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
          {m.leads_count}
          {m.hot_count > 0 && (
            <span style={{ color: "var(--hot)", fontSize: 11.5 }}> · {m.hot_count}</span>
          )}
        </td>
        <td>
          <Progress done={m.calls_today} plan={m.target_calls_day} label={t("team.ov.calls")} />
        </td>
        <td>
          <Progress done={m.goals_7d} plan={m.target_goals_week} label={t("team.ov.goals")} />
        </td>
        <td>
          <TelephonyCell m={m} />
        </td>
        <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
          {m.can_set_targets && (
            <button
              type="button"
              className="btn-icon"
              onClick={() => toggle("targets")}
              title={t("team.ov.setPlan")}
              style={panel === "targets" ? { color: "var(--accent)" } : undefined}
            >
              <Icon name="zap" size={13} />
            </button>
          )}
          {m.can_edit && (
            <button
              type="button"
              className="btn-icon"
              onClick={() => toggle("edit")}
              title={t("common.edit")}
              style={panel === "edit" ? { color: "var(--accent)" } : undefined}
            >
              <Icon name="pencil" size={13} />
            </button>
          )}
          {m.can_view_as && (
            <button
              type="button"
              className="btn-icon"
              onClick={viewAs}
              title={t("team.owner.viewAs")}
            >
              <Icon name="eye" size={13} />
            </button>
          )}
          {m.can_remove && (
            <button
              type="button"
              className="btn-icon"
              onClick={startRemove}
              disabled={busy}
              title={t("team.member.remove")}
              style={{ color: "var(--cold)" }}
            >
              <Icon name="trash" size={13} />
            </button>
          )}
        </td>
      </tr>

      {panel !== "none" && (
        <tr>
          <td colSpan={7} style={{ background: "var(--surface-2)", padding: "10px 14px" }}>
            {panel === "targets" && (
              <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
                <label style={{ fontSize: 12 }}>
                  <div style={{ color: "var(--text-dim)", marginBottom: 4 }}>
                    {t("team.ov.planCalls")}
                  </div>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={1000}
                    value={tCalls}
                    onChange={(e) => setTCalls(e.target.value)}
                    style={{ width: 90 }}
                  />
                </label>
                <label style={{ fontSize: 12 }}>
                  <div style={{ color: "var(--text-dim)", marginBottom: 4 }}>
                    {t("team.ov.planGoals")}
                  </div>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={1000}
                    value={tGoals}
                    onChange={(e) => setTGoals(e.target.value)}
                    style={{ width: 90 }}
                  />
                </label>
                <button type="button" className="btn btn-sm" disabled={busy} onClick={saveTargets}>
                  {busy ? t("common.loading") : t("common.save")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setPanel("none")}
                >
                  {t("common.cancel")}
                </button>
                <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>
                  {t("team.ov.planHint")}
                </span>
              </div>
            )}

            {panel === "edit" && (
              <div style={{ display: "grid", gap: 8 }}>
                <textarea
                  className="textarea"
                  rows={2}
                  value={desc}
                  maxLength={1000}
                  onChange={(e) => setDesc(e.target.value)}
                  placeholder={t("team.member.descriptionPh")}
                />
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    className="input"
                    value={ext}
                    onChange={(e) => setExt(e.target.value)}
                    placeholder={t("team.ov.extPh")}
                    style={{ width: 260, fontFamily: "var(--font-mono)", fontSize: 12 }}
                  />
                  <button type="button" className="btn btn-sm" disabled={busy} onClick={saveEdit}>
                    {busy ? t("common.loading") : t("common.save")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setPanel("none")}
                  >
                    {t("common.cancel")}
                  </button>
                </div>
              </div>
            )}

            {panel === "transfer" && (
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12.5 }}>
                <span>{t("team.member.transferPrompt")}</span>
                <select
                  className="select"
                  value={transferPick}
                  onChange={(e) =>
                    setTransferPick(e.target.value ? Number(e.target.value) : "")
                  }
                  style={{ fontSize: 12, padding: "4px 8px", width: "auto" }}
                >
                  <option value="">{t("team.member.transferPick")}</option>
                  {all
                    .filter((x) => x.id !== m.id)
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.name}
                      </option>
                    ))}
                </select>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={busy || transferPick === ""}
                  onClick={() => doRemove(transferPick as number)}
                >
                  {busy ? t("common.loading") : t("team.member.transferAndRemove")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setPanel("none")}
                >
                  {t("common.cancel")}
                </button>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function toMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
