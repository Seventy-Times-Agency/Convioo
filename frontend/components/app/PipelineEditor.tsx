"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  TAG_COLORS,
  TAG_COLOR_HEX,
  createLeadStatus,
  deleteLeadStatus,
  listLeadStatuses,
  reorderLeadStatuses,
  updateLeadStatus,
  type LeadStatusItem,
  type TagColor,
} from "@/lib/api";

/**
 * Per-team pipeline editor: rename, recolor, reorder (drag), add and
 * remove status columns. Backend rejects deleting a status still
 * attached to live leads (HTTP 409) — we surface that error inline.
 */
export function PipelineEditor({ teamId }: { teamId: string }) {
  const [items, setItems] = useState<LeadStatusItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftKey, setDraftKey] = useState("");
  const [draftLabel, setDraftLabel] = useState("");
  const [draftColor, setDraftColor] = useState<TagColor>("slate");
  const [creating, setCreating] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listLeadStatuses(teamId)
      .then((r) => {
        if (!cancelled) setItems(r.items);
      })
      .catch((e) => {
        if (!cancelled) setError(toMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const patch = async (
    id: string,
    body: Parameters<typeof updateLeadStatus>[2],
  ) => {
    setError(null);
    try {
      const updated = await updateLeadStatus(teamId, id, body);
      setItems((prev) => prev.map((it) => (it.id === id ? updated : it)));
    } catch (e) {
      setError(toMessage(e));
    }
  };

  const remove = async (id: string) => {
    setError(null);
    try {
      await deleteLeadStatus(teamId, id);
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (e) {
      setError(toMessage(e));
    }
  };

  const create = async () => {
    const key = draftKey.trim().toLowerCase();
    const label = draftLabel.trim();
    if (!key || !label) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createLeadStatus(teamId, {
        key,
        label,
        color: draftColor,
      });
      setItems((prev) => [...prev, created]);
      setDraftKey("");
      setDraftLabel("");
      setDraftColor("slate");
    } catch (e) {
      setError(toMessage(e));
    } finally {
      setCreating(false);
    }
  };

  const moveTo = async (sourceId: string, targetId: string) => {
    if (sourceId === targetId) return;
    const order = items.map((i) => i.id);
    const from = order.indexOf(sourceId);
    const to = order.indexOf(targetId);
    if (from < 0 || to < 0) return;
    order.splice(from, 1);
    order.splice(to, 0, sourceId);
    // Optimistic reorder so the drop animates immediately.
    setItems((prev) => order.map((id) => prev.find((p) => p.id === id)!));
    try {
      const r = await reorderLeadStatuses(teamId, order);
      setItems(r.items);
    } catch (e) {
      setError(toMessage(e));
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 6 }}>
        Pipeline
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>
        Этапы воронки
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 16,
        }}
      >
        Колонки канбана и статусы лидов берутся отсюда. Перетаскивайте,
        чтобы изменить порядок. Удалить можно только пустой этап.
      </div>

      {loading && (
        <div style={{ fontSize: 13, color: "var(--text-dim)" }}>Загрузка…</div>
      )}

      {!loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((it) => {
            const hex =
              TAG_COLOR_HEX[(it.color as TagColor) ?? "slate"] ??
              TAG_COLOR_HEX.slate;
            const isDropTarget = dropTargetId === it.id && dragId !== it.id;
            return (
              <div
                key={it.id}
                draggable
                onDragStart={(e) => {
                  setDragId(it.id);
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", it.id);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (dropTargetId !== it.id) setDropTargetId(it.id);
                }}
                onDragLeave={() => {
                  if (dropTargetId === it.id) setDropTargetId(null);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  const sourceId =
                    dragId ?? e.dataTransfer.getData("text/plain");
                  setDropTargetId(null);
                  setDragId(null);
                  if (sourceId) void moveTo(sourceId, it.id);
                }}
                onDragEnd={() => {
                  setDragId(null);
                  setDropTargetId(null);
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "8px 10px",
                  borderRadius: 10,
                  border: isDropTarget
                    ? "1px dashed var(--accent)"
                    : "1px solid var(--border)",
                  background: isDropTarget
                    ? "color-mix(in srgb, var(--accent) 8%, var(--surface-2))"
                    : "var(--surface-2)",
                  opacity: dragId === it.id ? 0.55 : 1,
                  cursor: "grab",
                  userSelect: "none",
                }}
              >
                <Icon
                  name="grid"
                  size={14}
                  style={{ color: "var(--text-dim)" }}
                />
                <span
                  aria-hidden
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: hex,
                    flexShrink: 0,
                  }}
                />
                <input
                  className="input"
                  value={it.label}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((p) =>
                        p.id === it.id ? { ...p, label: e.target.value } : p,
                      ),
                    )
                  }
                  onBlur={(e) => {
                    const next = e.target.value.trim();
                    if (next && next !== it.label) {
                      void patch(it.id, { label: next });
                    } else if (!next) {
                      // Revert empty edits.
                      setItems((prev) =>
                        prev.map((p) =>
                          p.id === it.id ? { ...p, label: it.label } : p,
                        ),
                      );
                    }
                  }}
                  style={{
                    fontSize: 13.5,
                    padding: "5px 9px",
                    flex: 1,
                    minWidth: 120,
                  }}
                />
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--text-dim)",
                    background: "var(--surface)",
                    padding: "2px 6px",
                    borderRadius: 6,
                  }}
                  title="Внутренний ключ. Не меняется."
                >
                  {it.key}
                </span>
                <select
                  value={(it.color as TagColor) ?? "slate"}
                  onChange={(e) =>
                    void patch(it.id, { color: e.target.value })
                  }
                  className="input"
                  style={{ fontSize: 12, padding: "5px 8px", width: 108 }}
                >
                  {TAG_COLORS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 11.5,
                    color: "var(--text-muted)",
                    whiteSpace: "nowrap",
                  }}
                  title="Закрытый этап (won / archived). Лиды на нём не учитываются в активной воронке."
                >
                  <input
                    type="checkbox"
                    checked={it.is_terminal}
                    onChange={(e) =>
                      void patch(it.id, { is_terminal: e.target.checked })
                    }
                  />
                  закрыт
                </label>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    if (
                      typeof window !== "undefined" &&
                      !window.confirm(
                        `Удалить этап «${it.label}»?\nЛиды на нём не будут затронуты, но колонка пропадёт.`,
                      )
                    ) {
                      return;
                    }
                    void remove(it.id);
                  }}
                  style={{
                    fontSize: 11,
                    padding: "4px 8px",
                    color: "var(--cold)",
                  }}
                  aria-label="Удалить этап"
                >
                  <Icon name="x" size={12} />
                </button>
              </div>
            );
          })}
          {items.length === 0 && (
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-dim)",
                padding: "12px 4px",
              }}
            >
              Нет ни одного этапа. Добавьте хотя бы один, чтобы лиды могли
              перемещаться.
            </div>
          )}
        </div>
      )}

      <div
        style={{
          marginTop: 14,
          paddingTop: 14,
          borderTop: "1px solid var(--border)",
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <input
          className="input"
          value={draftKey}
          onChange={(e) => setDraftKey(e.target.value)}
          placeholder="key (qualified)"
          style={{
            fontSize: 12.5,
            padding: "6px 10px",
            width: 150,
            fontFamily: "var(--font-mono)",
          }}
          maxLength={32}
        />
        <input
          className="input"
          value={draftLabel}
          onChange={(e) => setDraftLabel(e.target.value)}
          placeholder="Название (Квалифицированы)"
          style={{ fontSize: 13, padding: "6px 10px", flex: 1, minWidth: 180 }}
          maxLength={64}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void create();
            }
          }}
        />
        <select
          value={draftColor}
          onChange={(e) => setDraftColor(e.target.value as TagColor)}
          className="input"
          style={{ fontSize: 12, padding: "6px 8px", width: 108 }}
        >
          {TAG_COLORS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => void create()}
          disabled={creating || !draftKey.trim() || !draftLabel.trim()}
        >
          <Icon name="plus" size={12} /> Добавить
        </button>
      </div>

      {error && (
        <div
          style={{
            marginTop: 12,
            fontSize: 12.5,
            color: "var(--cold)",
            lineHeight: 1.5,
          }}
        >
          {error}
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
