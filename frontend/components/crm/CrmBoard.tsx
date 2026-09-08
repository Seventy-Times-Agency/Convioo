"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/ui";
import { LeadDetailModal } from "@/components/app/LeadDetailModal";
import { PipelineEditor } from "@/components/app/PipelineEditor";
import {
  createLeadStatus,
  getAllLeads,
  getTeamDetail,
  tempOf,
  updateLead,
  leadMarkHex,
  type Lead,
} from "@/lib/api";
import { statusColorHex, useTeamLeadStatuses } from "@/lib/leadStatuses";
import { getCurrentUser } from "@/lib/auth";
import {
  activeTeamId,
  subscribeWorkspace,
} from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

/**
 * CRM — доска, и только доска. Один тонкий тулбар: поиск, «Ведёт»,
 * сумма пайплайна, настройка колонок. Всё второстепенное убрано —
 * список, экспорт и массовые операции остаются в Базе, где им место.
 * Ориентир — зрелые доски (Pipedrive/Attio): колонка = этап, деньги
 * в шапке, карточка прыгает перетаскиванием.
 */
export function CrmBoard() {
  const { t } = useLocale();
  const { statuses, refresh: refreshStatuses } = useTeamLeadStatuses();

  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [tick, setTick] = useState(0);
  const [search, setSearch] = useState("");
  const [assignee, setAssignee] = useState("all");
  const [members, setMembers] = useState<{ id: number; name: string }[]>([]);
  const [myRole, setMyRole] = useState<string | null>(null);
  const [active, setActive] = useState<Lead | null>(null);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [dense, setDense] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [newCol, setNewCol] = useState("");
  const dragEndAt = useRef(0);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    try {
      setDense(window.localStorage.getItem("convioo.crm.dense") === "1");
      setCollapsed(
        new Set(
          JSON.parse(
            window.localStorage.getItem("convioo.crm.collapsed") ?? "[]",
          ) as string[],
        ),
      );
    } catch {
      /* приватный режим */
    }
  }, []);

  useEffect(() => {
    const teamId = activeTeamId();
    let cancelled = false;
    getAllLeads({
      limit: 500,
      bucket: "crm",
      teamId,
      memberUserId:
        assignee !== "all" && assignee !== "free"
          ? Number(assignee)
          : undefined,
      freeOnly: assignee === "free",
    })
      .then((d) => {
        if (!cancelled) setLeads(d.leads);
      })
      .catch((e) =>
        showError(e instanceof Error ? e.message : String(e)),
      );
    if (teamId) {
      getTeamDetail(teamId)
        .then((d) => {
          if (cancelled) return;
          setMyRole(d.role);
          const me = getCurrentUser();
          const mine = d.members.find((m) => m.id === me?.user_id);
          const scoped =
            d.role === "manager" && mine?.squad_id
              ? d.members.filter((m) => m.squad_id === mine.squad_id)
              : d.members;
          setMembers(scoped.map((m) => ({ id: m.id, name: m.name })));
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [tick, assignee]);

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

  const pipeline = useMemo(
    () => shown.reduce((sum, l) => sum + (l.deal_value ?? 0), 0),
    [shown],
  );

  const memberName = (id: number) =>
    members.find((m) => m.id === id)?.name ?? `#${id}`;

  const canEdit =
    Boolean(activeTeamId()) && myRole !== null && myRole !== "sales";

  const move = async (leadId: string, target: string) => {
    const lead = (leads ?? []).find((l) => l.id === leadId);
    if (!lead || lead.lead_status === target) return;
    const prev = lead.lead_status;
    setLeads(
      (rows) =>
        rows?.map((l) =>
          l.id === leadId ? { ...l, lead_status: target } : l,
        ) ?? null,
    );
    try {
      await updateLead(leadId, { lead_status: target });
    } catch (e) {
      setLeads(
        (rows) =>
          rows?.map((l) =>
            l.id === leadId ? { ...l, lead_status: prev } : l,
          ) ?? null,
      );
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const toggleCollapse = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      try {
        window.localStorage.setItem(
          "convioo.crm.collapsed",
          JSON.stringify(Array.from(next)),
        );
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  const addColumn = async () => {
    const label = newCol.trim();
    const teamId = activeTeamId();
    if (!label || !teamId) return;
    try {
      const slug =
        label
          .toLowerCase()
          .replace(/[^a-z0-9а-яёіїє]+/gi, "_")
          .replace(/^_+|_+$/g, "")
          .slice(0, 24) || "col";
      await createLeadStatus(teamId, {
        key: `${slug}_${Math.random().toString(36).slice(2, 6)}`,
        label,
      });
      setNewCol("");
      refreshStatuses();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  const scorePill = (l: Lead) => {
    const score = Math.round(l.score_ai ?? 0);
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
          flexShrink: 0,
          fontSize: 11,
          fontWeight: 800,
          fontVariantNumeric: "tabular-nums",
          color,
        }}
      >
        {score}
      </span>
    );
  };

  return (
    <>
      <Topbar title={t("crm.title")} />
      <div
        className="page"
        style={{ maxWidth: "100%", paddingBottom: 8 }}
      >
        {/* Один тонкий тулбар — как в зрелых досках */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 16,
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
              width: 260,
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

          {canEdit && (
            <select
              className="input"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              style={{ width: "auto", fontSize: 13, padding: "7px 10px" }}
            >
              <option value="all">{t("crm.assignee.all")}</option>
              <option value="free">{t("crm.assignee.free")}</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          )}

          <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
            {pipeline > 0 && (
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: "var(--text-muted)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {t("crm.pipeline.label")}: $
                {Math.round(pipeline).toLocaleString("en-US")}
              </span>
            )}
            <button
              type="button"
              className={`btn btn-sm ${dense ? "btn-primary" : "btn-ghost"}`}
              onClick={() => {
                setDense((v) => {
                  try {
                    window.localStorage.setItem(
                      "convioo.crm.dense",
                      v ? "0" : "1",
                    );
                  } catch {
                    /* ignore */
                  }
                  return !v;
                });
              }}
              title={t("crm.board.denseHint")}
            >
              {t("crm.board.dense")}
            </button>
            {canEdit && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setColumnsOpen(true)}
              >
                <Icon name="settings" size={13} />
                {t("crm.board.columns")}
              </button>
            )}
          </div>
        </div>

        {/* Доска */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              statuses
                .map((st) =>
                  collapsed.has(st.key) ? "44px" : "minmax(230px, 1fr)",
                )
                .join(" ") + (canEdit ? " 180px" : ""),
            gap: 12,
            overflowX: "auto",
            alignItems: "start",
            paddingBottom: 6,
          }}
        >
          {statuses.map((status) => {
            const col = status.key;
            const items = shown.filter((l) => l.lead_status === col);
            const colorHex = statusColorHex(col, statuses);
            const colSum = items.reduce(
              (sum, l) => sum + (l.deal_value ?? 0),
              0,
            );
            if (collapsed.has(col)) {
              return (
                <div
                  key={status.id}
                  onClick={() => toggleCollapse(col)}
                  title={`${status.label} · ${items.length}`}
                  style={{
                    background: "var(--surface-2)",
                    borderRadius: 12,
                    minHeight: 420,
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "12px 0",
                    gap: 10,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: colorHex,
                    }}
                  />
                  <span
                    style={{
                      writingMode: "vertical-rl",
                      fontSize: 11.5,
                      fontWeight: 700,
                      color: "var(--text-muted)",
                    }}
                  >
                    {status.label} · {items.length}
                  </span>
                </div>
              );
            }
            const dragActive = dragOver === col;
            return (
              <div
                key={status.id}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (dragOver !== col) setDragOver(col);
                }}
                onDragLeave={() => {
                  if (dragOver === col) setDragOver(null);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(null);
                  const id = e.dataTransfer.getData("text/plain");
                  if (id) void move(id, col);
                }}
                style={{
                  background: dragActive
                    ? "color-mix(in srgb, var(--accent) 10%, var(--surface-2))"
                    : "var(--surface-2)",
                  border: dragActive
                    ? "1px dashed var(--accent)"
                    : "1px solid transparent",
                  borderRadius: 12,
                  minHeight: 420,
                  display: "flex",
                  flexDirection: "column",
                  transition: "background .15s, border-color .15s",
                }}
              >
                {/* Шапка колонки: цвет · имя · счёт · $ */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "12px 14px 10px",
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      background: colorHex,
                      flexShrink: 0,
                    }}
                  />
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 800,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {status.label}
                  </span>
                  <span
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-dim)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {items.length}
                  </span>
                  <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                    {colSum > 0 && (
                      <span
                        style={{
                          fontSize: 11,
                          fontWeight: 800,
                          color: "var(--accent)",
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        ${Math.round(colSum).toLocaleString("en-US")}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleCollapse(col)}
                      title={t("crm.board.collapse")}
                      style={{
                        border: "none",
                        background: "none",
                        cursor: "pointer",
                        color: "var(--text-dim)",
                        padding: 0,
                        lineHeight: 1,
                      }}
                    >
                      <Icon name="chevronLeft" size={12} />
                    </button>
                  </span>
                </div>

                {/* Карточки */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    padding: "0 10px 12px",
                  }}
                >
                  {items.map((l) => {
                    const markHex = leadMarkHex(l.mark_color);
                    return (
                      <div
                        key={l.id}
                        className="card card-hover"
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData("text/plain", l.id);
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onDragEnd={() => {
                          dragEndAt.current = Date.now();
                        }}
                        onClick={() => {
                          if (Date.now() - dragEndAt.current < 200) return;
                          setActive(l);
                        }}
                        style={{
                          padding: dense ? "8px 12px" : "10px 12px",
                          cursor: "grab",
                          userSelect: "none",
                          borderLeft: markHex
                            ? `3px solid ${markHex}`
                            : undefined,
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 8,
                          }}
                        >
                          <span
                            style={{
                              fontSize: 13,
                              fontWeight: 700,
                              minWidth: 0,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {l.name}
                          </span>
                          {scorePill(l)}
                        </div>
                        {!dense && (
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              gap: 8,
                              marginTop: 4,
                              fontSize: 11,
                              color: "var(--text-dim)",
                            }}
                          >
                            <span
                              style={{
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {canEdit
                                ? l.owner_user_id
                                  ? memberName(l.owner_user_id)
                                  : t("crm.table.free")
                                : (l.category ?? l.address ?? "")}
                            </span>
                            {(l.deal_value ?? 0) > 0 && (
                              <span
                                style={{
                                  flexShrink: 0,
                                  fontWeight: 700,
                                  color: "var(--text-muted)",
                                  fontVariantNumeric: "tabular-nums",
                                }}
                              >
                                ${Math.round(l.deal_value ?? 0)}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {items.length === 0 && (
                    <div
                      style={{
                        fontSize: 11.5,
                        color: "var(--text-dim)",
                        textAlign: "center",
                        padding: "16px 6px",
                      }}
                    >
                      {t("crm.kanban.empty")}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {canEdit && (
            <div
              style={{
                border: "1.5px dashed var(--border)",
                borderRadius: 12,
                padding: 12,
                display: "flex",
                flexDirection: "column",
                gap: 8,
                alignSelf: "start",
              }}
            >
              <span className="eyebrow" style={{ fontSize: 10 }}>
                {t("crm.board.newColumn")}
              </span>
              <input
                className="input"
                value={newCol}
                onChange={(e) => setNewCol(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void addColumn();
                }}
                placeholder={t("crm.board.newColumnPh")}
                style={{ fontSize: 12.5, padding: "7px 10px" }}
              />
            </div>
          )}
        </div>

        <div
          style={{
            marginTop: 10,
            fontSize: 11.5,
            color: "var(--text-dim)",
          }}
        >
          {t("crm.board.footnote")}
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

      {canEdit && (
        <Modal
          open={columnsOpen}
          onClose={() => {
            setColumnsOpen(false);
            refreshStatuses();
          }}
          title={t("crm.board.columnsTitle")}
          width={620}
        >
          {activeTeamId() && (
            <PipelineEditor teamId={activeTeamId() as string} />
          )}
        </Modal>
      )}
    </>
  );
}
