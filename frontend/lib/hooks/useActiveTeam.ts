"use client";

import { useEffect, useState } from "react";
import { listMyTeams } from "@/lib/api";
import { normalizeRole } from "@/lib/roles";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";

/** Активная команда и моя роль в ней — для экранов, где от роли
 * зависит, что показывать. ``role === null`` — ещё грузится или
 * личный режим. */
export function useActiveTeam(): { teamId: string | undefined; role: string | null } {
  const [teamId, setTeamId] = useState<string | undefined>(() => activeTeamId());
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => subscribeWorkspace(() => setTeamId(activeTeamId())), []);
  useEffect(() => {
    if (!teamId) {
      setRole(null);
      return;
    }
    let cancelled = false;
    listMyTeams()
      .then((rows) => {
        if (cancelled) return;
        const me = rows.find((r) => r.id === teamId);
        setRole(me ? normalizeRole(me.role) : null);
      })
      .catch(() => !cancelled && setRole(null));
    return () => {
      cancelled = true;
    };
  }, [teamId]);
  return { teamId, role };
}
