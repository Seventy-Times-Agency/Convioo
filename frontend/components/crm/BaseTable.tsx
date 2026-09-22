"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { EmptyState } from "@/components/app/EmptyState";
import { LeadDetailModal } from "@/components/app/LeadDetailModal";
import {
  distributeBase,
  getAllLeads,
  getTeamDetail,
  listFunnels,
  tempOf,
  updateTeam,
  type Funnel,
  type Lead,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

/**
 * База — сырьё после добычи, максимально простой стол: поиск,
 * чекбоксы, «Раздать». Никаких досок, статусов и настроек — у
 * нетронутого лида есть только одна судьба: попасть к селзу.
 */
export function BaseTable() {
  const { t } = useLocale();
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [tick, setTick] = useState(0);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [members, setMembers] = useState<{ id: number; name: string }[]>([]);
  const [funnels, setFunnels] = useState<Funnel[]>([]);
  const [funnelId, setFunnelId] = useState("");
  const [userId, setUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<Lead | null>(null);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [autoOn, setAutoOn] = useState(false);
  // Авто-раздача при заходе срабатывает один раз за визит.
  const autoRan = useRef(false);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    const teamId = activeTeamId();
    let cancelled = false;
    getAllLeads({ limit: 500, bucket: "base", teamId })
      .then((d) => {
        if (!cancelled) setLeads(d.leads);
      })
      .catch((e) => showError(e instanceof Error ? e.message : String(e)));
    if (teamId) {
      getTeamDetail(teamId)
        .then((d) => {
          if (cancelled) return;
          setMyRole(d.role);
          setAutoOn(Boolean(d.auto_distribute));
          const me = getCurrentUser();
          const mine = d.members.find((m) => m.id === me?.user_id);
          const scoped =
            d.role === "manager" && mine?.squad_id
              ? d.members.filter((m) => m.squad_id === mine.squad_id)
              : d.members;
          setMembers(scoped.map((m) => ({ id: m.id, name: m.name })));
          // Автораспределение включено — при заходе База раздаёт
          // сырьё сама, один раз за визит.
          if (d.auto_distribute && !autoRan.current) {
            autoRan.current = true;
            distributeBase(teamId, { mode: "auto" })
              .then((r) => {
                if (r.assigned > 0) {
                  showSuccess(
                    t("base.autoRan", {
                      n: r.assigned,
                      split: Object.entries(r.split)
                        .map(([name, n]) => `${name} — ${n}`)
                        .join(", "),
                    }),
                  );
                  setTick((n) => n + 1);
                }
              })
              .catch(() => undefined);
          }
        })
        .catch(() => undefined);
      listFunnels(teamId)
        .then(setFunnels)
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
    // t — для текста тоста авто-раздачи; повторный прогон безопасен:
    // autoRan не даёт раздать дважды за визит.
  }, [tick, t]);

  const shown = useMemo(() => {
    const rows = leads ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((l) =>
      [l.name, l.address, l.category]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [leads, search]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allShownSelected =
    shown.length > 0 && shown.every((l) => selected.has(l.id));

  const toggleAll = () =>
    setSelected(
      allShownSelected ? new Set() : new Set(shown.map((l) => l.id)),
    );

  const run = async (
    mode: "auto" | "selected" | "manual",
  ) => {
    const teamId = activeTeamId();
    if (!teamId || busy) return;
    if (mode !== "auto" && selected.size === 0) return;
    if (mode === "manual" && !userId) return;
    setBusy(true);
    try {
      const r = await distributeBase(teamId, {
        mode,
        leadIds: mode === "auto" ? undefined : Array.from(selected),
        ownerUserId: mode === "manual" ? Number(userId) : undefined,
        funnelId: funnelId || undefined,
      });
      setSelected(new Set());
      setTick((n) => n + 1);
      showSuccess(
        t("base.distributedSplit", {
          n: r.assigned,
          split: Object.entries(r.split)
            .map(([name, k]) => `${name} — ${k}`)
            .join(", "),
        }),
      );
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleAuto = async () => {
    const teamId = activeTeamId();
    if (!teamId) return;
    const next = !autoOn;
    setAutoOn(next);
    try {
      await updateTeam(teamId, { auto_distribute: next });
    } catch (e) {
      setAutoOn(!next);
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const scoreCell = (l: Lead) => {
    const temp = tempOf(l.score_ai);
    const color =
      temp === "hot"
        ? "var(--hot)"
        : temp === "warm"
          ? "var(--warm)"
          : "var(--text-dim)";
    return (
      <span
        style={{
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          color,
        }}
      >
        {Math.round(l.score_ai ?? 0)}
      </span>
    );
  };

  return (
    <>
      <Topbar title={t("base.title")} subtitle={t("base.subtitle")} />
      <div className="page" style={{ maxWidth: 1200 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 14,
            flexWrap: "wrap",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "7px 12px",
              width: 280,
            }}
          >
            <Icon
              name="search"
              size={14}
              style={{ color: "var(--text-dim)", flexShrink: 0 }}
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("crm.search.placeholder")}
              style={{
                border: "none",
                outline: "none",
                background: "transparent",
                width: "100%",
                fontSize: 13,
                color: "var(--text)",
              }}
            />
          </div>
          <span
            style={{
              fontSize: 12.5,
              color: "var(--text-dim)",
            }}
          >
            {t("base.count", { n: shown.length })}
          </span>
          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              gap: 8,
              alignItems: "center",
            }}
          >
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy}
              onClick={() => void run("auto")}
              title={t("base.autoAllHint")}
            >
              {t("base.autoAll")}
            </button>
            {(myRole === "owner" || myRole === "admin") && (
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 12,
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}
                title={t("base.autoToggleHint")}
              >
                <input
                  type="checkbox"
                  checked={autoOn}
                  onChange={() => void toggleAuto()}
                  style={{ accentColor: "var(--accent)" }}
                />
                {t("base.autoToggle")}
              </label>
            )}
          </div>
        </div>

        {selected.size > 0 && (
          <div
            style={{
              position: "sticky",
              top: 0,
              zIndex: 40,
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
              padding: "10px 14px",
              marginBottom: 12,
              borderRadius: 12,
              background:
                "color-mix(in srgb, var(--accent) 8%, var(--surface))",
              border:
                "1px solid color-mix(in srgb, var(--accent) 30%, var(--border))",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 700 }}>
              {t("crm.bulk.selected", { n: selected.size })}
            </span>
            <select
              className="input"
              value={funnelId}
              onChange={(e) => setFunnelId(e.target.value)}
              style={{ width: 180, fontSize: 12.5, padding: "6px 9px" }}
              title={t("base.funnelOptHint")}
            >
              <option value="">{t("base.funnelOpt")}</option>
              {funnels.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy}
              onClick={() => void run("selected")}
              title={t("base.fairHint")}
            >
              {t("base.fairSelected", { n: selected.size })}
            </button>
            <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {t("base.orExact")}
            </span>
            <select
              className="input"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              style={{ width: 150, fontSize: 12.5, padding: "6px 9px" }}
            >
              <option value="">{t("base.pickRep")}</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy || !userId}
              onClick={() => void run("manual")}
            >
              {t("base.giveExact")}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setSelected(new Set())}
            >
              {t("common.cancel")}
            </button>
          </div>
        )}

        {leads !== null && leads.length === 0 ? (
          <div className="card" style={{ padding: 28 }}>
            <EmptyState
              icon="search"
              title={t("base.emptyTitle")}
              body={t("base.emptyBody")}
              actions={[
                { label: t("base.goMine"), href: "/app/search" },
              ]}
            />
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="tbl" style={{ minWidth: 760 }}>
                <thead>
                  <tr>
                    <th style={{ width: 34 }}>
                      <input
                        type="checkbox"
                        checked={allShownSelected}
                        onChange={toggleAll}
                        style={{ accentColor: "var(--accent)" }}
                      />
                    </th>
                    <th>{t("base.col.company")}</th>
                    <th>{t("base.col.where")}</th>
                    <th style={{ width: 70 }}>{t("base.col.score")}</th>
                    <th style={{ width: 130 }}>{t("base.col.owner")}</th>
                    <th style={{ width: 110 }}>{t("base.col.added")}</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((l) => (
                    <tr
                      key={l.id}
                      style={{ cursor: "pointer" }}
                      onClick={() => setActive(l)}
                    >
                      <td onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selected.has(l.id)}
                          onChange={() => toggle(l.id)}
                          style={{ accentColor: "var(--accent)" }}
                        />
                      </td>
                      <td style={{ fontWeight: 700 }}>{l.name}</td>
                      <td
                        style={{
                          fontSize: 12.5,
                          color: "var(--text-muted)",
                          maxWidth: 340,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {[l.category, l.address]
                          .filter(Boolean)
                          .join(" · ")}
                      </td>
                      <td>{scoreCell(l)}</td>
                      <td
                        style={{
                          fontSize: 12,
                          fontWeight: l.owner_user_id ? 700 : 400,
                          color: l.owner_user_id
                            ? "var(--accent)"
                            : "var(--text-dim)",
                        }}
                      >
                        {l.owner_user_id
                          ? (members.find(
                              (m) => m.id === l.owner_user_id,
                            )?.name ?? `#${l.owner_user_id}`)
                          : t("base.unassigned")}
                      </td>
                      <td
                        style={{
                          fontSize: 12,
                          color: "var(--text-dim)",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {new Date(l.created_at).toLocaleDateString(
                          "ru-RU",
                          { day: "numeric", month: "short" },
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {active && (
        <LeadDetailModal
          lead={active}
          onClose={() => {
            setActive(null);
            setTick((n) => n + 1);
          }}
        />
      )}
    </>
  );
}
