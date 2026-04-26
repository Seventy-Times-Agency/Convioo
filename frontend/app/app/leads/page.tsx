"use client";

import { useEffect, useMemo, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { LeadCard } from "@/components/app/LeadCard";
import { LeadDetailModal } from "@/components/app/LeadDetailModal";
import {
  type Lead,
  type LeadListResponse,
  type LeadMarkColor,
  type LeadStatus,
  LEAD_MARK_COLORS,
  LEAD_MARK_HEX,
  bulkUpdateLeads,
  getAllLeads,
  leadMarkHex,
  tempOf,
} from "@/lib/api";
import {
  activeMemberUserId,
  activeTeamId,
  subscribeWorkspace,
} from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";

type View = "list" | "kanban" | "grid";
type Filter = "all" | LeadStatus;
type SortKey =
  | "score_desc"
  | "score_asc"
  | "created_desc"
  | "created_asc"
  | "touched_desc"
  | "name_asc"
  | "name_desc";

const STATUS_ORDER: LeadStatus[] = [
  "new",
  "contacted",
  "replied",
  "won",
  "archived",
];

const SORT_OPTIONS: SortKey[] = [
  "score_desc",
  "score_asc",
  "touched_desc",
  "created_desc",
  "created_asc",
  "name_asc",
  "name_desc",
];

const SORT_STORAGE_KEY = "convioo.crm.sort";

export default function LeadsCRMPage() {
  const { t } = useLocale();
  const [data, setData] = useState<LeadListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("list");
  const [filter, setFilter] = useState<Filter>("all");
  const [active, setActive] = useState<Lead | null>(null);
  const [tick, setTick] = useState(0);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("score_desc");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  // Pick up persisted sort on mount; persist again whenever it changes.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(SORT_STORAGE_KEY);
    if (stored && (SORT_OPTIONS as string[]).includes(stored)) {
      setSort(stored as SortKey);
    }
  }, []);
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SORT_STORAGE_KEY, sort);
  }, [sort]);

  useEffect(() => {
    let cancelled = false;
    getAllLeads({
      limit: 500,
      teamId: activeTeamId(),
      memberUserId: activeMemberUserId(),
    })
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const sessions = data?.sessions_by_id ?? {};
  const leads = data?.leads ?? [];

  const filtered = useMemo(() => {
    let out = filter === "all" ? leads : leads.filter((l) => l.lead_status === filter);
    const q = search.trim().toLowerCase();
    if (q) {
      out = out.filter((l) => {
        const haystack = [l.name, l.address, l.category]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      });
    }
    const sorted = [...out];
    const tsOf = (s: string | null) =>
      s ? new Date(s).getTime() : 0;
    sorted.sort((a, b) => {
      switch (sort) {
        case "score_desc":
          return (b.score_ai ?? -1) - (a.score_ai ?? -1);
        case "score_asc":
          return (a.score_ai ?? 999) - (b.score_ai ?? 999);
        case "created_desc":
          return tsOf(b.created_at) - tsOf(a.created_at);
        case "created_asc":
          return tsOf(a.created_at) - tsOf(b.created_at);
        case "touched_desc":
          return tsOf(b.last_touched_at) - tsOf(a.last_touched_at);
        case "name_asc":
          return a.name.localeCompare(b.name);
        case "name_desc":
          return b.name.localeCompare(a.name);
        default:
          return 0;
      }
    });
    return sorted;
  }, [filter, leads, search, sort]);

  const statusCounts = useMemo(() => {
    const counts: Record<LeadStatus, number> = {
      new: 0,
      contacted: 0,
      replied: 0,
      won: 0,
      archived: 0,
    };
    for (const l of leads) counts[l.lead_status]++;
    return counts;
  }, [leads]);

  const relative = (ts: string): string => {
    const then = new Date(ts).getTime();
    if (Number.isNaN(then)) return t("common.none");
    const diff = Date.now() - then;
    const m = Math.floor(diff / 60000);
    if (m < 1) return t("crm.relative.now");
    if (m < 60) return t("crm.relative.m", { n: m });
    const h = Math.floor(m / 60);
    if (h < 24) return t("crm.relative.h", { n: h });
    const d = Math.floor(h / 24);
    return t("crm.relative.d", { n: d });
  };

  const updateLocalLead = (updated: Lead) => {
    setData((d) =>
      d
        ? {
            ...d,
            leads: d.leads.map((l) => (l.id === updated.id ? updated : l)),
          }
        : d,
    );
  };

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    setSelected((prev) => {
      const visibleIds = new Set(filtered.map((l) => l.id));
      const allSelected = filtered.length > 0 && filtered.every((l) => prev.has(l.id));
      if (allSelected) {
        const next = new Set(prev);
        for (const id of visibleIds) next.delete(id);
        return next;
      }
      const next = new Set(prev);
      for (const id of visibleIds) next.add(id);
      return next;
    });
  };

  const clearSelection = () => setSelected(new Set());

  const applyBulkStatus = async (status: LeadStatus) => {
    if (selected.size === 0) return;
    setBulkBusy(true);
    setBulkError(null);
    try {
      await bulkUpdateLeads({
        leadIds: Array.from(selected),
        leadStatus: status,
      });
      setData((d) =>
        d
          ? {
              ...d,
              leads: d.leads.map((l) =>
                selected.has(l.id)
                  ? {
                      ...l,
                      lead_status: status,
                      last_touched_at: new Date().toISOString(),
                    }
                  : l,
              ),
            }
          : d,
      );
      clearSelection();
    } catch (e) {
      setBulkError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const applyBulkMark = async (color: LeadMarkColor | null) => {
    if (selected.size === 0) return;
    setBulkBusy(true);
    setBulkError(null);
    try {
      await bulkUpdateLeads({
        leadIds: Array.from(selected),
        markColor: color,
      });
      setData((d) =>
        d
          ? {
              ...d,
              leads: d.leads.map((l) =>
                selected.has(l.id) ? { ...l, mark_color: color } : l,
              ),
            }
          : d,
      );
      clearSelection();
    } catch (e) {
      setBulkError(e instanceof Error ? e.message : String(e));
    } finally {
      setBulkBusy(false);
    }
  };

  return (
    <>
      {selected.size > 0 && (
        <div
          style={{
            position: "sticky",
            top: 0,
            zIndex: 50,
            padding: "10px 16px",
            background:
              "linear-gradient(135deg, color-mix(in srgb, var(--accent) 12%, var(--surface)), var(--surface))",
            borderBottom:
              "1px solid color-mix(in srgb, var(--accent) 30%, var(--border))",
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {t("crm.bulk.selected", { n: selected.size })}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="eyebrow" style={{ fontSize: 9 }}>
              {t("crm.bulk.setStatus")}
            </span>
            {STATUS_ORDER.map((s) => (
              <button
                key={s}
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => applyBulkStatus(s)}
                disabled={bulkBusy}
                style={{ fontSize: 12, padding: "4px 10px" }}
              >
                {t(`lead.statusLabel.${s}` as TranslationKey)}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="eyebrow" style={{ fontSize: 9 }}>
              {t("crm.bulk.setMark")}
            </span>
            {LEAD_MARK_COLORS.map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => applyBulkMark(c)}
                disabled={bulkBusy}
                title={c}
                aria-label={c}
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  background: LEAD_MARK_HEX[c],
                  border: "2px solid transparent",
                  cursor: bulkBusy ? "wait" : "pointer",
                }}
              />
            ))}
            <button
              type="button"
              onClick={() => applyBulkMark(null)}
              disabled={bulkBusy}
              style={{
                fontSize: 11,
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-dim)",
                padding: "2px 6px",
              }}
            >
              {t("lead.mark.clear")}
            </button>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={clearSelection}
            disabled={bulkBusy}
            style={{ marginLeft: "auto" }}
          >
            <Icon name="x" size={12} />
            {t("crm.bulk.cancel")}
          </button>
          {bulkError && (
            <div
              style={{
                fontSize: 12,
                color: "var(--cold)",
                width: "100%",
              }}
            >
              {bulkError}
            </div>
          )}
        </div>
      )}
      <Topbar
        title={t("crm.title")}
        subtitle={t("crm.subtitle", {
          leads: leads.length,
          sessions: Object.keys(sessions).length,
        })}
        right={
          <button className="btn btn-ghost btn-sm" type="button" disabled>
            <Icon name="download" size={14} /> {t("common.export")}
          </button>
        }
      />
      <div className="page">
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

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 12,
          }}
        >
          <div
            style={{
              position: "relative",
              flex: 1,
              maxWidth: 360,
            }}
          >
            <Icon
              name="search"
              size={14}
              style={{
                position: "absolute",
                left: 12,
                top: "50%",
                transform: "translateY(-50%)",
                color: "var(--text-dim)",
              }}
            />
            <input
              className="input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("crm.search.placeholder")}
              style={{ paddingLeft: 34, fontSize: 13.5 }}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                style={{
                  position: "absolute",
                  right: 8,
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  padding: 4,
                  cursor: "pointer",
                  color: "var(--text-dim)",
                }}
                aria-label={t("crm.search.clear")}
              >
                <Icon name="x" size={12} />
              </button>
            )}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              color: "var(--text-muted)",
            }}
          >
            <Icon name="sortDesc" size={13} />
            <select
              className="input"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              style={{ fontSize: 13, padding: "8px 10px" }}
            >
              {SORT_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {t(`crm.sort.${s}` as TranslationKey)}
                </option>
              ))}
            </select>
          </div>
          <div
            style={{
              marginLeft: "auto",
              fontSize: 12,
              color: "var(--text-dim)",
              whiteSpace: "nowrap",
            }}
          >
            {t("crm.search.results", { n: filtered.length })}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 16,
            gap: 12,
          }}
        >
          <div className="seg">
            <button
              type="button"
              className={filter === "all" ? "active" : ""}
              onClick={() => setFilter("all")}
            >
              {t("crm.status.all")} · {leads.length}
            </button>
            {STATUS_ORDER.map((s) => (
              <button
                key={s}
                type="button"
                className={filter === s ? "active" : ""}
                onClick={() => setFilter(s)}
              >
                {t(`crm.status.${s}` as TranslationKey)} · {statusCounts[s]}
              </button>
            ))}
          </div>
          <div className="seg">
            <button
              type="button"
              className={view === "list" ? "active" : ""}
              onClick={() => setView("list")}
            >
              <Icon name="list" size={14} />
            </button>
            <button
              type="button"
              className={view === "kanban" ? "active" : ""}
              onClick={() => setView("kanban")}
            >
              <Icon name="kanban" size={14} />
            </button>
            <button
              type="button"
              className={view === "grid" ? "active" : ""}
              onClick={() => setView("grid")}
            >
              <Icon name="grid" size={14} />
            </button>
          </div>
        </div>

        {leads.length === 0 && !error && (
          <div
            className="card"
            style={{
              padding: 32,
              textAlign: "center",
              color: "var(--text-muted)",
            }}
          >
            {t("crm.empty")}
          </div>
        )}

        {view === "list" && filtered.length > 0 && (
          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 36 }}>
                    <input
                      type="checkbox"
                      aria-label={t("crm.bulk.selectAll")}
                      checked={
                        filtered.length > 0 &&
                        filtered.every((l) => selected.has(l.id))
                      }
                      onChange={toggleSelectAllVisible}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </th>
                  <th />
                  <th>{t("crm.table.lead")}</th>
                  <th>{t("crm.table.session")}</th>
                  <th>{t("crm.table.score")}</th>
                  <th>{t("crm.table.status")}</th>
                  <th>{t("crm.table.touched")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((l) => {
                  const session = sessions[l.query_id];
                  const score = Math.round(l.score_ai ?? 0);
                  const temp = tempOf(l.score_ai);
                  const isSelected = selected.has(l.id);
                  return (
                    <tr
                      key={l.id}
                      style={{
                        cursor: "pointer",
                        background: isSelected
                          ? "color-mix(in srgb, var(--accent) 6%, transparent)"
                          : undefined,
                      }}
                      onClick={() => setActive(l)}
                    >
                      <td
                        style={{ width: 36 }}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSelected(l.id);
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelected(l.id)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </td>
                      <td style={{ width: 32 }}>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                          }}
                        >
                          <span className={"status-dot " + temp} />
                          {leadMarkHex(l.mark_color) && (
                            <span
                              style={{
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                background: leadMarkHex(l.mark_color)!,
                              }}
                            />
                          )}
                        </div>
                      </td>
                      <td>
                        <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                          {l.name}
                        </div>
                        <div
                          style={{ fontSize: 11.5, color: "var(--text-muted)" }}
                        >
                          {l.address}
                        </div>
                      </td>
                      <td>
                        {session ? (
                          <span className="chip" style={{ fontSize: 11 }}>
                            {session.niche} · {session.region}
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-dim)" }}>
                            {t("common.none")}
                          </span>
                        )}
                      </td>
                      <td>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontWeight: 700,
                            color:
                              score >= 75
                                ? "var(--hot)"
                                : score >= 50
                                  ? "#B45309"
                                  : "var(--cold)",
                          }}
                        >
                          {score}
                        </span>
                      </td>
                      <td>
                        <span className="chip" style={{ fontSize: 11 }}>
                          {t(
                            `lead.statusLabel.${l.lead_status}` as TranslationKey,
                          )}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {l.last_touched_at
                          ? relative(l.last_touched_at)
                          : t("common.none")}
                      </td>
                      <td>
                        <Icon
                          name="chevronRight"
                          size={14}
                          style={{ color: "var(--text-dim)" }}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {view === "kanban" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(5, 1fr)",
              gap: 14,
            }}
          >
            {STATUS_ORDER.map((col) => {
              const items = leads.filter((l) => l.lead_status === col);
              return (
                <div
                  key={col}
                  style={{
                    background: "var(--surface-2)",
                    borderRadius: 12,
                    padding: 12,
                    minHeight: 400,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: 12,
                      padding: "0 4px",
                    }}
                  >
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      {t(`lead.statusLabel.${col}` as TranslationKey)}
                    </div>
                    <div
                      className="chip"
                      style={{ fontSize: 11, background: "var(--surface)" }}
                    >
                      {items.length}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {items.map((l) => {
                      const score = Math.round(l.score_ai ?? 0);
                      const temp = tempOf(l.score_ai);
                      const markHex = leadMarkHex(l.mark_color);
                      return (
                        <div
                          key={l.id}
                          className="card"
                          style={{
                            padding: 12,
                            cursor: "pointer",
                            borderLeft: markHex ? `3px solid ${markHex}` : undefined,
                          }}
                          onClick={() => setActive(l)}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              marginBottom: 6,
                            }}
                          >
                            <span className={"status-dot " + temp} />
                            <span
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: 12,
                                fontWeight: 700,
                                color: score >= 75 ? "var(--hot)" : "#B45309",
                              }}
                            >
                              {score}
                            </span>
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                            {l.name}
                          </div>
                          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            {l.address}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {view === "grid" && filtered.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 14,
            }}
          >
            {filtered.map((l) => (
              <LeadCard key={l.id} lead={l} onClick={() => setActive(l)} />
            ))}
          </div>
        )}
      </div>

      {active && (
        <LeadDetailModal
          lead={active}
          onClose={() => setActive(null)}
          onUpdated={updateLocalLead}
        />
      )}
    </>
  );
}
