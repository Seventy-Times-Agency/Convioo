import { request } from "./_core";

export interface HomeTile {
  key: string;
  label: string;
  value: string;
  hint: string;
}

export interface HomeWeekPoint {
  label: string;
  count: number;
}

export interface HomeMemberRow {
  user_id: number;
  name: string;
  dials: number;
  goals: number;
  lagging: boolean;
}

export interface HomeEventRow {
  at: string;
  text: string;
}

export interface HomeCallbackRow {
  lead_id: string;
  lead_name: string;
  at: string | null;
  hint: string | null;
  overdue: boolean;
}

export interface HomeReactionRow {
  lead_id: string;
  lead_name: string;
  category: string;
  preview: string;
  at: string;
  has_draft: boolean;
}

export interface TeamHome {
  role: string;
  scope: string;
  tiles: HomeTile[];
  weekly: HomeWeekPoint[];
  members: HomeMemberRow[];
  events: HomeEventRow[];
  queue_total: number;
  next_callback_at: string | null;
  free_leads: number;
  /** Счёт дня для шапки прозвона. «Разговоры» — наборы, где сняли
   *  трубку; длительности нет, телефония ещё не подключена. */
  dials_today: number;
  conversations_today: number;
  goals_today: number;
  /** Экран селза (Home.dc): приветствие и план на сейчас. */
  first_name: string;
  letters_pending: number;
  callbacks: HomeCallbackRow[];
  reactions: HomeReactionRow[];
}

export async function getTeamHome(teamId: string): Promise<TeamHome> {
  return request<TeamHome>(`/api/v1/teams/${teamId}/home`);
}
