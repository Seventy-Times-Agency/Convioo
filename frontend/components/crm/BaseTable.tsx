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
  archiveSearch,
  baseBulk,
  deleteSearch,
  distributeBase,
  getAllLeads,
  getBaseFacets,
  getTeamDetail,
  listFunnels,
  tempOf,
  restoreSearch,
  updateTeam,
  type BaseBulkAction,
  type BaseFacets,
  type BaseTab,
  type BaseFilters,
  type BaseSort,
  type Funnel,
  type Lead,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

const PANEL_KEY = "convioo.base.panel.";
const FILTERS_MODE_KEY = "convioo.base.filtersMode";

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
  // Как показывать панель: по ширине экрана (auto), всегда слева
  // (pinned) или свёрнутой (hidden). Выбор запоминается в браузере.
  const [filtersMode, setFiltersModeState] = useState<"auto" | "pinned" | "hidden">("auto");
  useEffect(() => {
    try {
      const v = window.localStorage.getItem(FILTERS_MODE_KEY);
      if (v === "pinned" || v === "hidden") setFiltersModeState(v);
    } catch {
      // без памяти — по ширине экрана
    }
  }, []);
  const setFiltersMode = (m: "auto" | "pinned" | "hidden") => {
    setFiltersModeState(m);
    setFiltersOpen(false);
    try {
      window.localStorage.setItem(FILTERS_MODE_KEY, m);
    } catch {
      // не запомним — не страшно
    }
  };
  const [isWide, setIsWide] = useState(true);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1280px)");
    const sync = () => setIsWide(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  // При нажатии — по текущей ширине, а не по запомненной.
  const wide = () => (typeof window !== "undefined" ? window.matchMedia("(min-width: 1280px)").matches : isWide);
  const onFiltersButton = () => {
    if (wide()) setFiltersMode(filtersMode === "hidden" ? "auto" : "hidden");
    else if (filtersMode === "pinned") setFiltersMode("auto");
    else setFiltersOpen((v) => !v);
  };
  const onCollapse = () => {
    if (wide()) setFiltersMode("hidden");
    else if (filtersMode === "pinned") setFiltersMode("auto");
    else setFiltersOpen(false);
  };
  const [tab, setTab] = useState<BaseTab>("work");
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
      sessions: panel.sessions ?? [],
      sort: sort.key,
      order: sort.order,
    }),
    [q, panel, sort],
  );

  useEffect(() => {
    const teamId = activeTeamId();
    let cancelled = false;
    getAllLeads({
      limit: 500,
      teamId,
      filters,
      ...(tab === "archive" ? { archived: true } : { bucket: tab === "no_contact" ? "no_contact" : "base" }),
    })
      .then((d) => {
        if (cancelled) return;
        setLeads(d.leads);
        setTotal(d.total);
        setSessions(d.sessions_by_id ?? {});
      })
      .catch((e) => !cancelled && showError(e instanceof Error ? e.message : String(e)));
    getBaseFacets(teamId, filters, tab)
      .then((f) => !cancelled && setFacets(f))
      .catch(() => !cancelled && setFacets(null));
    return () => {
      cancelled = true;
    };
  }, [tick, filters, tab]);

  const switchTab = (next: BaseTab) => {
    setTab(next);
    setSelected(new Set());
  };

  const canDelete = !!myRole && ["owner", "tech", "admin"].includes(myRole);

  const bulk = async (action: BaseBulkAction) => {
    const teamId = activeTeamId();
    if (!teamId || busy || selected.size === 0) return;
    if (action === "delete" && !(await confirmAsync(t("base.confirmDelete", { n: selected.size })))) return;
    setBusy(true);
    try {
      const r = await baseBulk(teamId, Array.from(selected), action);
      setSelected(new Set());
      setTick((n) => n + 1);
      if (r.changed === 0) showSuccess(t("base.done.nothing"));
      else showSuccess(t(`base.done.${action}` as Parameters<typeof t>[0], { n: r.changed }));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sessionAction = async (id: string, action: "archive" | "restore" | "delete") => {
    if (action === "delete" && !(await confirmAsync(t("base.confirmSessionDelete")))) return;
    try {
      if (action === "archive") await archiveSearch(id);
      else if (action === "restore") await restoreSearch(id);
      else await deleteSearch(id);
      setPanel({ ...panel, sessions: [] });
      setTick((n) => n + 1);
      showSuccess(t(`base.session.${action}` as Parameters<typeof t>[0]));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

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
            className={"btn btn-ghost btn-sm bf-toggle" + (filtersOpen || filtersMode === "pinned" ? " on" : "")}
            onClick={onFiltersButton}
            aria-expanded={filtersOpen || filtersMode === "pinned"}
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

        {activeTeamId() && (
          <div className="seg bf-tabs" role="tablist" aria-label={t("base.tabs")}>
            {(["work", "no_contact", "archive"] as BaseTab[]).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={tab === k}
                className={tab === k ? "active" : ""}
                onClick={() => switchTab(k)}
              >
                {t(`base.tab.${k}` as Parameters<typeof t>[0])}
                {facets?.tabs && <span className="bf-tab-n">{facets.tabs[k]}</span>}
              </button>
            ))}
          </div>
        )}

        <div className={"bf-layout" + (filtersMode !== "auto" ? " " + filtersMode : "")}>
        <BaseFacetsPanel
          facets={facets}
          state={panel}
          onChange={setPanel}
          showOwners={Boolean(activeTeamId())}
          open={filtersOpen}
          onCollapse={onCollapse}
          onPin={!isWide && filtersMode !== "pinned" ? () => setFiltersMode("pinned") : undefined}
          sessionActions={
            activeTeamId() && myRole && myRole !== "sales"
              ? { archive: tab !== "archive", restore: tab === "archive", delete: canDelete }
              : undefined
          }
          onSessionAction={(id, a) => void sessionAction(id, a)}
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
            {tab === "work" && (
              <>
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
              </>
            )}
            {tab === "work" && (
              <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void bulk("unassign")} title={t("base.unassignHint")}>
                {t("base.unassign")}
              </button>
            )}
            {tab === "no_contact" && (
              <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void bulk("restore_contact")}>
                {t("base.restoreContact")}
              </button>
            )}
            {tab !== "archive" ? (
              <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void bulk("archive")}>
                {t("base.toArchive")}
              </button>
            ) : (
              <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void bulk("unarchive")}>
                {t("base.fromArchive")}
              </button>
            )}
            {canDelete && (
              <button type="button" className="btn btn-ghost btn-sm" style={{ color: "var(--cold)" }} disabled={busy} onClick={() => void bulk("delete")}>
                {t("common.delete")}
              </button>
            )}
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
