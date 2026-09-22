import { request } from "./_core";

export interface QueueLead {
  id: string;
  name: string;
  phone: string | null;
  score: number | null;
  bucket: "callback" | "hot" | "rest";
  next_touch_at: string | null;
  lead_status: string;
  funnel_id: string | null;
  business_language: string | null;
}

export interface WorkQueue {
  callbacks: QueueLead[];
  hot: QueueLead[];
  rest: QueueLead[];
  total: number;
}

export type CallOutcome =
  | "no_answer"
  | "wrong_number"
  | "refused"
  | "thinking"
  | "callback"
  | "goal";

export async function getWorkQueue(teamId: string): Promise<WorkQueue> {
  return request<WorkQueue>(
    `/api/v1/work/queue?team_id=${encodeURIComponent(teamId)}`,
  );
}

export async function postCallOutcome(
  leadId: string,
  outcome: CallOutcome,
  opts: { callbackAt?: string; note?: string } = {},
): Promise<{ ok: boolean; result: Record<string, unknown> }> {
  return request(`/api/v1/leads/${leadId}/call-outcome`, {
    method: "POST",
    body: JSON.stringify({
      outcome,
      callback_at: opts.callbackAt ?? null,
      note: opts.note ?? null,
    }),
  });
}

/** Строка очереди писем: лид, шаг воронки, когда уйдёт. */
export interface LetterRow {
  lead_id: string;
  lead_name: string;
  funnel_name: string | null;
  step_index: number;
  steps_total: number;
  note: string | null;
  due_at: string | null;
}

export interface WorkLetters {
  cap: number;
  sent_today: number;
  warmup_day: number;
  pending_approval: LetterRow[];
  scheduled: LetterRow[];
}

export async function getWorkLetters(teamId: string): Promise<WorkLetters> {
  return request<WorkLetters>(`/api/v1/work/letters?team_id=${teamId}`);
}

/** Пульт прозвона: живая картина по каждому сотруднику за сегодня. */
export interface WorkOverviewRow {
  user_id: number;
  name: string;
  role: string;
  squad_name: string | null;
  dials: number;
  talks: number;
  goals: number;
  overdue_callbacks: number;
  queue_total: number;
  last_call_at: string | null;
}

export interface WorkOverview {
  rows: WorkOverviewRow[];
  dials: number;
  talks: number;
  goals: number;
}

export async function getWorkOverview(
  teamId: string,
): Promise<WorkOverview> {
  return request<WorkOverview>(`/api/v1/teams/${teamId}/work/overview`);
}
