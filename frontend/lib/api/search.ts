import { request, requireUserId } from "./_core";
import { type LeadTemp } from "./leads";
import { type Lead } from "./leads";

export type SearchStatus = "pending" | "running" | "done" | "failed";

export interface SearchSummary {
  id: string;
  user_id: number;
  niche: string;
  region: string;
  status: SearchStatus;
  source: string;
  created_at: string;
  finished_at: string | null;
  leads_count: number;
  avg_score: number | null;
  hot_leads_count: number | null;
  error: string | null;
  insights: string | null;
}

export const SEARCH_SOURCES = [
  "google",
  "osm",
  "yelp",
  "foursquare",
] as const;
export type SearchSource = (typeof SEARCH_SOURCES)[number];

export const LEAD_LIMIT_CHOICES = [5, 10, 20, 30, 50] as const;
export type LeadLimitChoice = (typeof LEAD_LIMIT_CHOICES)[number];
export const DEFAULT_LEAD_LIMIT: LeadLimitChoice = 50;

export const SEARCH_SCOPES = ["city", "metro", "state", "country"] as const;
export type SearchScope = (typeof SEARCH_SCOPES)[number];
export const RADIUS_CHOICES_KM = [5, 10, 25, 50, 100] as const;
export type RadiusChoiceKm = (typeof RADIUS_CHOICES_KM)[number];

export interface CityEntry {
  id: string;
  name: string;
  country: string;
  lat: number;
  lon: number;
  population: number;
}

export interface SearchCreate {
  niche: string;
  region: string;
  user_id?: number;
  language_code?: string;
  target_languages?: string[];
  profession?: string;
  limit?: number;
  scope?: SearchScope;
  radius_km?: number;
  enabled_sources?: SearchSource[];
}

export interface SearchCreateResponse {
  id: string;
  queued: boolean;
}

export interface ConsultMessage {
  role: "user" | "assistant";
  content: string;
}

export type ConsultSlot =
  | "niche"
  | "region"
  | "ideal_customer"
  | "exclusions";

export interface ConsultResponse {
  reply: string;
  niche: string | null;
  region: string | null;
  ideal_customer: string | null;
  exclusions: string | null;
  ready: boolean;
  last_asked_slot: ConsultSlot | null;
}

export interface ConsultCurrentState {
  niche?: string | null;
  region?: string | null;
  ideal_customer?: string | null;
  exclusions?: string | null;
  last_asked_slot?: ConsultSlot | null;
}

export interface SearchAxisOption {
  niche: string;
  region: string;
  ideal_customer: string | null;
  exclusions: string | null;
  rationale: string | null;
}

export interface PriorTeamSearch {
  search_id: string;
  user_id: number;
  user_name: string;
  niche: string;
  region: string;
  leads_count: number;
  created_at: string;
}

export interface SearchPreflightResponse {
  blocked: boolean;
  matches: PriorTeamSearch[];
}

export type AssistantMode = "personal" | "team_member" | "team_owner";

export type AssistantField =
  | "display_name"
  | "age_range"
  | "business_size"
  | "service_description"
  | "home_region"
  | "niches";

export type PendingActionKind =
  | "profile_patch"
  | "team_description"
  | "member_description"
  | "launch_search";

export interface PendingAction {
  kind: PendingActionKind;
  summary: string;
  payload: Record<string, unknown>;
}

export interface AssistantResponse {
  reply: string;
  mode: AssistantMode;
  suggestion_summary: string | null;
  awaiting_field: AssistantField | null;
  pending_actions: PendingAction[] | null;
  applied_actions: PendingAction[] | null;
}

export interface CsvImportRow {
  name: string;
  website?: string | null;
  region?: string | null;
  phone?: string | null;
  category?: string | null;
  extras?: Record<string, string>;
}

export async function listCities(args: {
  q?: string | null;
  country?: string | null;
  lang?: string | null;
  limit?: number;
} = {}): Promise<{ items: CityEntry[]; query: string; language: string }> {
  const params = new URLSearchParams();
  if (args.q) params.set("q", args.q);
  if (args.country) params.set("country", args.country);
  if (args.lang) params.set("lang", args.lang);
  if (args.limit) params.set("limit", String(args.limit));
  const qs = params.toString();
  return request<{ items: CityEntry[]; query: string; language: string }>(
    `/api/v1/cities${qs ? "?" + qs : ""}`,
  );
}

export async function consultSearch(
  messages: ConsultMessage[],
  currentState: ConsultCurrentState = {},
): Promise<ConsultResponse> {
  return request<ConsultResponse>("/api/v1/search/consult", {
    method: "POST",
    body: JSON.stringify({
      user_id: requireUserId(),
      messages,
      current_niche: currentState.niche ?? null,
      current_region: currentState.region ?? null,
      current_ideal_customer: currentState.ideal_customer ?? null,
      current_exclusions: currentState.exclusions ?? null,
      last_asked_slot: currentState.last_asked_slot ?? null,
    }),
  });
}

export async function suggestSearchAxes(): Promise<{
  options: SearchAxisOption[];
}> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  return request<{ options: SearchAxisOption[] }>(
    `/api/v1/search/suggest-axes?${params.toString()}`,
    { method: "POST" },
  );
}

export async function preflightSearch(args: {
  niche: string;
  region: string;
  teamId?: string;
}): Promise<SearchPreflightResponse> {
  const params = new URLSearchParams({
    user_id: String(requireUserId()),
    niche: args.niche,
    region: args.region,
  });
  if (args.teamId) params.set("team_id", args.teamId);
  return request<SearchPreflightResponse>(
    `/api/v1/searches/preflight?${params.toString()}`,
  );
}

export async function createSearch(
  body: SearchCreate & { team_id?: string },
): Promise<SearchCreateResponse> {
  return request<SearchCreateResponse>("/api/v1/searches", {
    method: "POST",
    body: JSON.stringify({ user_id: requireUserId(), ...body }),
  });
}

export async function getSearches(
  opts: { userId?: number; teamId?: string; memberUserId?: number } = {},
): Promise<SearchSummary[]> {
  const id = opts.userId ?? requireUserId();
  const params = new URLSearchParams({ user_id: String(id), limit: "50" });
  if (opts.teamId) params.set("team_id", opts.teamId);
  if (opts.memberUserId !== undefined)
    params.set("member_user_id", String(opts.memberUserId));
  return request<SearchSummary[]>(`/api/v1/searches?${params.toString()}`);
}

export async function getSearch(id: string): Promise<SearchSummary> {
  return request<SearchSummary>(`/api/v1/searches/${id}`);
}

export async function getSearchLeads(
  id: string,
  temp?: LeadTemp,
): Promise<Lead[]> {
  const params = new URLSearchParams({ user_id: String(requireUserId()) });
  if (temp) params.set("temp", temp);
  return request<Lead[]>(`/api/v1/searches/${id}/leads?${params.toString()}`);
}

export async function assistantChat(
  messages: ConsultMessage[],
  opts: {
    teamId?: string;
    awaitingField?: AssistantField | null;
    pendingActions?: PendingAction[] | null;
  } = {},
): Promise<AssistantResponse> {
  return request<AssistantResponse>("/api/v1/assistant/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: requireUserId(),
      team_id: opts.teamId,
      messages,
      awaiting_field: opts.awaitingField ?? null,
      pending_actions: opts.pendingActions ?? null,
    }),
  });
}

export async function importLeadsCsv(input: {
  rows: CsvImportRow[];
  label?: string;
  teamId?: string;
}): Promise<{ search_id: string; inserted: number; skipped: number }> {
  return request<{ search_id: string; inserted: number; skipped: number }>(
    `/api/v1/searches/import-csv`,
    {
      method: "POST",
      body: JSON.stringify({
        user_id: requireUserId(),
        team_id: input.teamId ?? null,
        label: input.label ?? "CSV import",
        rows: input.rows,
      }),
    },
  );
}
