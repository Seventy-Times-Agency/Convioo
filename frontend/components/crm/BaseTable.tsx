"use client";

import { canAdminTeam } from "@/lib/roles";
import { useEffect, useMemo, useRef, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/brand/Icon";
import { EmptyState } from "@/components/shell/EmptyState";
import { LeadDetailModal } from "@/components/leads/LeadDetailModal";
import {
  BaseFacetsPanel,
  EMPTY_PANEL,
  panelIsEmpty,
  type BasePanelState,
} from "@/components/crm/BaseFacets";
import {
  distributeBase,
  getAllLeads,
  getBaseFacets,
  getTeamDetail,
  listFunnels,
  tempOf,
  updateTeam,
  type BaseFacets,
  type BaseFilters,
  type BaseSort,
  type Funnel,
  type Lead,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

const PANEL_KEY = "convioo.base.panel.";

function loadPanel(scope: string): BasePanelState {
  try {
    const raw = window.localStorage.getItem(PANEL_KEY + scope);
    return raw ? { ...EMPTY_PANEL, ...JSON.parse(raw) } : EMPTY_PANEL;
  } catch {
    return EMPTY_PANEL;
  }
}

function addedAfter(added: BasePanelState["added"]): string | undefined {
  if (!added) return undefined;
  const d = new Date();
  if (added === "day") d.setHours(0, 0, 0, 0);
  else d.setDate(d.getDate() - (added === "week" ? 7 : 30));
  return d.toISOString();
}

/**
 * База — сырьё после добычи: панель фильтров слева (кто ведёт, ниша,
 * город, оценка, контакты, дата — с количеством), таблица с
 * сортировкой по колонкам, чекбоксы и «Раздать». Отбор идёт на
 * сервере по всей базе; выбор фильтров запоминается.
 */
export function BaseTable() {
  const { t } = useLocale();
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [total, setTotal] = useState(0);
  const [sessions, setSessions] = useState<Record<string, { niche: string; region: string }>>({});
  const [facets, setFacets] = useState<BaseFacets | null>(null);
  const [tick, setTick] = useState(0);
  const [search, setSearch] = useState("");
  // На узком экране панель фильтров свёрнута в кнопку над таблицей,
  // чтобы таблица помещалась целиком.
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [q, setQ] = useState("");
  const scope = activeTeamId() ?? "personal";
  const [panel, setPanelState] = useState<BasePanelState>(EMPTY_PANEL);
  const [sort, setSort] = useState<{ key: BaseSort; order: "asc" | "desc" }>({ key: "score", order: "desc" });
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
    // Смена пространства: выбор, роль и список людей — от прошлой
    // команды, их нельзя нести в новую (иначе ID лидов команды A
    // уедут в раздачу команды B).
    setSelected(new Set());
    setMyRole(null);
    setMembers([]);
    setFunnels([]);
    autoRan.current = false;
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

  // Фильтры запоминаются отдельно для каждого пространства.
  useEffect(() => {
    setPanelState(loadPanel(scope));
  }, [scope]);
  const setPanel = (next: BasePanelState) => {
    setPanelState(next);
    setSelected(new Set());
    try {
      window.localStorage.setItem(PANEL_KEY + scope, JSON.stringify(next));
    } catch {
      // без памяти — просто не запомним
    }
  };

  // Поиск по тексту — на сервере, с небольшой паузой на ввод.
  useEffect(() => {
    const id = window.setTimeout(() => setQ(search), 300);
    return () => window.clearTimeout(id);
  }, [search]);

  const filters: BaseFilters = useMemo(
    () => ({
      q,
      owners: panel.owners,
      niches: panel.niches,
      regions: panel.regions,
      temps: panel.temps,
      hasPhone: panel.hasPhone,
      hasEmail: panel.hasEmail,
      noWebsite: panel.noWebsite,
      addedAfter: addedAfter(panel.added),
      sort: sort.key,
      order: sort.order,
    }),
    [q, panel, sort],
  );

  useEffect(() => {
    const teamId = activeTeamId();
    let cancelled = false;
    getAllLeads({ limit: 500, bucket: "base", teamId, filters })
      .then((d) => {
        if (cancelled) return;
        setLeads(d.leads);
        setTotal(d.total);
        setSessions(d.sessions_by_id ?? {});
      })
      .catch((e) => !cancelled && showError(e instanceof Error ? e.message : String(e)));
    getBaseFacets(teamId, filters)
      .then((f) => !cancelled && setFacets(f))
      .catch(() => !cancelled && setFacets(null));
    return () => {
      cancelled = true;
    };
  }, [tick, filters]);

  const sortBy = (key: BaseSort) =>
    setSort((s) =>
      s.key === key
        ? { key, order: s.order === "desc" ? "asc" : "desc" }
        : { key, order: key === "name" || key === "region" || key === "owner" ? "asc" : "desc" },
    );

  const shown = leads ?? [];

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

  const sortHead = (key: BaseSort, label: string, width?: number) => (
    <th style={width ? { width } : undefined}>
      <button
        type="button"
        className={"bf-sort" + (sort.key === key ? " on" : "")}
        onClick={() => sortBy(key)}
      >
        {label}
        <span aria-hidden="true">{sort.key === key ? (sort.order === "desc" ? " ↓" : " ↑") : " ↕"}</span>
      </button>
    </th>
  );

  return (
    <>
      <Topbar title={t("base.title")} subtitle={t("base.subtitle")} />
      <div className="page" style={{ maxWidth: 1400 }}>
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
          <button
            type="button"
            className={"btn btn-ghost btn-sm bf-toggle" + (filtersOpen ? " on" : "")}
            onClick={() => setFiltersOpen((v) => !v)}
            aria-expanded={filtersOpen}
          >
            <Icon name="filter" size={13} />
            {t("bf.title")}
            {!panelIsEmpty(panel) && <span className="bf-toggle-dot" aria-hidden="true" />}
          </button>
          <span
            style={{
              fontSize: 12.5,
              color: "var(--text-dim)",
            }}
          >
            {t("base.found", { n: total })}
            {shown.length < total ? ` · ${t("base.firstN", { n: shown.length })}` : ""}
          </span>
          {activeTeamId() && (
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
            {canAdminTeam(myRole) && (
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
          )}
        </div>

        <div className="bf-layout">
        <BaseFacetsPanel
          facets={facets}
          state={panel}
          onChange={setPanel}
          showOwners={Boolean(activeTeamId())}
          open={filtersOpen}
        />
        <div style={{ minWidth: 0 }}>
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
            {panelIsEmpty(panel) && !q ? (
              <EmptyState
                icon="search"
                title={t("base.emptyTitle")}
                body={t("base.emptyBody")}
                actions={[{ label: t("base.goMine"), href: "/app/search" }]}
              />
            ) : (
              <EmptyState
                icon="search"
                title={t("bf.nothing")}
                body={t("bf.nothingBody")}
                actions={[
                  {
                    label: t("bf.reset"),
                    onClick: () => {
                      setSearch("");
                      setPanel(EMPTY_PANEL);
                    },
                  },
                ]}
              />
            )}
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table className="tbl" style={{ minWidth: 820 }}>
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
                    {sortHead("name", t("base.col.company"))}
                    <th>{t("bf.col.niche")}</th>
                    {sortHead("region", t("bf.col.city"))}
                    {sortHead("score", t("base.col.score"), 80)}
                    <th style={{ width: 90 }}>{t("bf.col.contacts")}</th>
                    {sortHead("owner", t("base.col.owner"), 130)}
                    {sortHead("created", t("base.col.added"), 100)}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((l) => {
                    const sess = sessions[l.query_id];
                    return (
                      <tr key={l.id} style={{ cursor: "pointer" }} onClick={() => setActive(l)}>
                        <td onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selected.has(l.id)}
                            onChange={() => toggle(l.id)}
                            style={{ accentColor: "var(--accent)" }}
                          />
                        </td>
                        <td style={{ maxWidth: 280 }}>
                          <div style={{ fontWeight: 700 }}>{l.name}</div>
                          <div className="bf-sub">{[l.category, l.address].filter(Boolean).join(" · ")}</div>
                        </td>
                        <td>{sess?.niche ? <span className="bf-niche">{sess.niche}</span> : "—"}</td>
                        <td style={{ fontSize: 12.5, color: "var(--text-muted)", whiteSpace: "nowrap" }}>{sess?.region ?? "—"}</td>
                        <td>{scoreCell(l)}</td>
                        <td>
                          <span className="bf-contacts">
                            <span className={l.phone ? "y" : ""} title={l.phone ?? t("bf.noPhone")}>☎</span>
                            <span className={l.contact_email ? "y" : ""} title={l.contact_email ?? t("bf.noEmail")}>@</span>
                            <span className={l.website ? "y" : ""} title={l.website ?? t("bf.noWebsite")}>◎</span>
                          </span>
                        </td>
                        <td
                          style={{
                            fontSize: 12,
                            fontWeight: l.owner_user_id ? 700 : 400,
                            color: l.owner_user_id ? "var(--accent)" : "var(--text-dim)",
                          }}
                        >
                          {l.owner_user_id
                            ? (members.find((m) => m.id === l.owner_user_id)?.name ??
                              facets?.owners.find((o) => o.id === l.owner_user_id)?.name ??
                              `#${l.owner_user_id}`)
                            : t("base.unassigned")}
                        </td>
                        <td style={{ fontSize: 12, color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>
                          {new Date(l.created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
        </div>
        </div>
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
