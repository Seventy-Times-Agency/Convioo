"use client";

import { useEffect, useMemo, useState } from "react";
import {
  TAG_COLOR_HEX,
  listLeadStatuses,
  type LeadStatusItem,
  type TagColor,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";

// Labels resolve through the i18n dictionary (lead.statusLabel.*) so the
// personal-mode fallback palette follows the active language. Team palettes
// come from the server and carry their own labels.
const LEGACY_FALLBACK_DEFS: Array<{
  id: string;
  key: string;
  labelKey: TranslationKey;
  color: string;
  order_index: number;
  is_terminal: boolean;
}> = [
  { id: "_legacy_new", key: "new", labelKey: "lead.statusLabel.new", color: "slate", order_index: 0, is_terminal: false },
  { id: "_legacy_contacted", key: "contacted", labelKey: "lead.statusLabel.contacted", color: "blue", order_index: 1, is_terminal: false },
  { id: "_legacy_replied", key: "replied", labelKey: "lead.statusLabel.replied", color: "teal", order_index: 2, is_terminal: false },
  { id: "_legacy_won", key: "won", labelKey: "lead.statusLabel.won", color: "green", order_index: 3, is_terminal: true },
  { id: "_legacy_archived", key: "archived", labelKey: "lead.statusLabel.archived", color: "slate", order_index: 99, is_terminal: true },
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
  const { t } = useLocale();
  const fallback = useMemo<LeadStatusItem[]>(
    () =>
      LEGACY_FALLBACK_DEFS.map((d) => ({
        id: d.id,
        key: d.key,
        label: t(d.labelKey),
        color: d.color,
        order_index: d.order_index,
        is_terminal: d.is_terminal,
      })),
    [t],
  );
  const [teamId, setTeamId] = useState<string | null>(
    () => activeTeamId() ?? null,
  );
  const [statuses, setStatuses] = useState<LeadStatusItem[]>(fallback);
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
      setStatuses(fallback);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listLeadStatuses(teamId)
      .then((r) => {
        if (cancelled) return;
        setStatuses(r.items.length > 0 ? r.items : fallback);
      })
      .catch(() => {
        if (!cancelled) setStatuses(fallback);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [teamId, fallback]);

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
