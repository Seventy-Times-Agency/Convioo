"use client";

import { TAG_COLOR_HEX, type LeadTag, type TagColor } from "@/lib/api";

/**
 * Read-only tag chip rendering. Used on lead cards / list rows where
 * we just want to show the tags without an editor.
 */
export function TagChips({
  tags,
  size = "sm",
}: {
  tags: LeadTag[];
  size?: "xs" | "sm";
}) {
  if (!tags.length) return null;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
      }}
    >
      {tags.map((tag) => (
        <TagChip key={tag.id} tag={tag} size={size} />
      ))}
    </div>
  );
}

export function TagChip({
  tag,
  size = "sm",
  onRemove,
}: {
  tag: LeadTag;
  size?: "xs" | "sm";
  onRemove?: () => void;
}) {
  const hex = TAG_COLOR_HEX[tag.color as TagColor] ?? TAG_COLOR_HEX.slate;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: size === "xs" ? "1px 7px" : "2px 9px",
        fontSize: size === "xs" ? 10 : 11.5,
        fontWeight: 600,
        borderRadius: 999,
        background: `color-mix(in srgb, ${hex} 18%, transparent)`,
        color: hex,
        border: `1px solid color-mix(in srgb, ${hex} 35%, transparent)`,
        lineHeight: 1.5,
      }}
    >
      {tag.name}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Убрать тег ${tag.name}`}
          style={{
            border: "none",
            background: "transparent",
            color: hex,
            cursor: "pointer",
            padding: 0,
            fontSize: size === "xs" ? 11 : 12,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      )}
    </span>
  );
}
