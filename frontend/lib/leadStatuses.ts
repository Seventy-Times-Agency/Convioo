"use client";

import { useEffect, useState } from "react";
import {
  TAG_COLOR_HEX,
  listLeadStatuses,
  type LeadStatusItem,
  type TagColor,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";

const LEGACY_FALLBACK: LeadStatusItem[] = [
  { id: "_legacy_new", key: "new", label: "новый", color: "slate", order_index: 0, is_terminal: false },
  { id: "_legacy_contacted", key: "contacted", label: "в работе", color: "blue", order_index: 1, is_terminal: false },
  { id: "_legacy_replied", key: "replied", label: "ответил", color: "teal", order_index: 2, is_terminal: false },
  { id: "_legacy_won", key: "won", label: "сделка", color: "green", order_index: 3, is_terminal: true },
  { id: "_legacy_archived", key: "archived", label: "архив", color: "slate", order_index: 99, is_terminal: true },
];

/**
 * Subscribe to the active team's lead-status palette. Falls back to
 * the five legacy keys (new/contacted/replied/won/archived) when no
 * team is active or the fetch fails — that matches the seeded
 * server-side palette so a personal-mode lead's existing status
 * always renders.
 */
export function useTeamLeadStatuses(): {
  statuses: LeadStatusItem[];
  loading: boolean;
} {
  const [teamId, setTeamId] = useState<string | null>(
    () => activeTeamId() ?? null,
  );
  const [statuses, setStatuses] = useState<LeadStatusItem[]>(LEGACY_FALLBACK);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(
    () =>
      subscribeWorkspace(() => {
        setTeamId(activeTeamId() ?? null);
      }),
    [],
  );

  useEffect(() => {
    if (!teamId) {
      setStatuses(LEGACY_FALLBACK);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listLeadStatuses(teamId)
      .then((r) => {
        if (cancelled) return;
        setStatuses(r.items.length > 0 ? r.items : LEGACY_FALLBACK);
      })
      .catch(() => {
        if (!cancelled) setStatuses(LEGACY_FALLBACK);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  return { statuses, loading };
}

export function statusLabel(
  key: string | null | undefined,
  statuses: LeadStatusItem[],
): string {
  if (!key) return "";
  const found = statuses.find((s) => s.key === key);
  if (found) return found.label;
  // Unknown key — best-effort capitalize so it stays readable.
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export function statusColorHex(
  key: string | null | undefined,
  statuses: LeadStatusItem[],
): string {
  const found = key ? statuses.find((s) => s.key === key) : undefined;
  const color = (found?.color as TagColor) ?? "slate";
  return TAG_COLOR_HEX[color] ?? TAG_COLOR_HEX.slate;
}
