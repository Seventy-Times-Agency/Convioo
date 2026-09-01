import { request } from "./_core";

export interface JournalEntry {
  id: string;
  at: string;
  actor_id: number | null;
  actor_name: string | null;
  actor_role: string | null;
  kind: string;
  payload: Record<string, unknown> | null;
  object_label: string | null;
}

export interface JournalResponse {
  entries: JournalEntry[];
  kinds: string[];
}

export async function getTeamJournal(
  teamId: string,
  opts: { kind?: string; actorId?: number; days?: number } = {},
): Promise<JournalResponse> {
  const p = new URLSearchParams();
  if (opts.kind) p.set("kind", opts.kind);
  if (opts.actorId != null) p.set("actor_id", String(opts.actorId));
  if (opts.days) p.set("days", String(opts.days));
  const qs = p.toString();
  return request<JournalResponse>(
    `/api/v1/teams/${teamId}/journal${qs ? `?${qs}` : ""}`,
  );
}
