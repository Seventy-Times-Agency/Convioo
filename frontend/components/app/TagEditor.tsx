"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  TAG_COLORS,
  TAG_COLOR_HEX,
  assignLeadTags,
  createTag,
  listTags,
  type LeadTag,
  type TagColor,
} from "@/lib/api";
import { TagChip } from "@/components/app/TagChips";

/**
 * Inline tag editor for the lead detail modal. Shows the current
 * chips, lets the user toggle palette tags on/off, and create new
 * ones inline. Persists the full tag set via PUT
 * ``/api/v1/leads/{id}/tags`` so the operation is idempotent — the
 * caller always sees the canonical post-state.
 */
export function TagEditor({
  leadId,
  initialTags,
  teamId,
  onChanged,
}: {
  leadId: string;
  initialTags: LeadTag[];
  teamId?: string | null;
  onChanged?: (tags: LeadTag[]) => void;
}) {
  const [palette, setPalette] = useState<LeadTag[]>([]);
  const [active, setActive] = useState<LeadTag[]>(initialTags);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftColor, setDraftColor] = useState<TagColor>("blue");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setActive(initialTags);
  }, [initialTags]);

  useEffect(() => {
    if (!editing) return;
    let cancelled = false;
    listTags(teamId ?? null)
      .then((r) => {
        if (!cancelled) setPalette(r.items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [editing, teamId]);

  const persist = async (next: LeadTag[]) => {
    setSaving(true);
    setError(null);
    try {
      const result = await assignLeadTags(
        leadId,
        next.map((t) => t.id),
      );
      setActive(result.items);
      onChanged?.(result.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const toggle = (tag: LeadTag) => {
    const present = active.some((t) => t.id === tag.id);
    void persist(present ? active.filter((t) => t.id !== tag.id) : [...active, tag]);
  };

  const createInline = async () => {
    const name = draftName.trim();
    if (!name) return;
    setCreating(true);
    setError(null);
    try {
      const tag = await createTag({
        name,
        color: draftColor,
        teamId: teamId ?? null,
      });
      setPalette((prev) => [...prev, tag]);
      setDraftName("");
      // Auto-attach the freshly created tag to this lead.
      void persist([...active, tag]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 6,
          alignItems: "center",
        }}
      >
        {active.map((tag) => (
          <TagChip
            key={tag.id}
            tag={tag}
            onRemove={editing ? () => toggle(tag) : undefined}
          />
        ))}
        {!editing && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setEditing(true)}
            style={{ padding: "2px 9px", fontSize: 11.5 }}
          >
            {active.length === 0 ? "+ Добавить теги" : "Редактировать"}
          </button>
        )}
        {editing && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setEditing(false)}
            style={{ padding: "2px 9px", fontSize: 11.5 }}
            disabled={saving || creating}
          >
            Готово
          </button>
        )}
      </div>

      {editing && (
        <div
          style={{
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: 10,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: "var(--text-dim)",
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            Палитра
          </div>
          {palette.length === 0 ? (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Пусто. Создайте первый тег ниже.
            </div>
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {palette.map((tag) => {
                const on = active.some((t) => t.id === tag.id);
                return (
                  <button
                    key={tag.id}
                    type="button"
                    onClick={() => toggle(tag)}
                    disabled={saving}
                    style={{
                      padding: "2px 9px",
                      fontSize: 11.5,
                      borderRadius: 999,
                      border: `1px solid ${on ? "var(--accent)" : "var(--border)"}`,
                      background: on
                        ? `color-mix(in srgb, ${
                            TAG_COLOR_HEX[tag.color as TagColor] ?? TAG_COLOR_HEX.slate
                          } 14%, transparent)`
                        : "var(--surface-2)",
                      color: on
                        ? TAG_COLOR_HEX[tag.color as TagColor] ?? TAG_COLOR_HEX.slate
                        : "var(--text)",
                      fontWeight: on ? 600 : 500,
                      cursor: "pointer",
                    }}
                  >
                    {tag.name}
                  </button>
                );
              })}
            </div>
          )}

          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              className="input"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              placeholder="Название нового тега"
              style={{ flex: 1, fontSize: 12, padding: "5px 9px" }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void createInline();
                }
              }}
            />
            <select
              value={draftColor}
              onChange={(e) => setDraftColor(e.target.value as TagColor)}
              className="input"
              style={{
                fontSize: 12,
                padding: "5px 8px",
                width: 100,
              }}
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
              disabled={creating || !draftName.trim()}
              onClick={() => void createInline()}
            >
              + Добавить
            </button>
          </div>
          {error && (
            <div style={{ fontSize: 12, color: "var(--cold)" }}>{error}</div>
          )}
        </div>
      )}
    </div>
  );
}
