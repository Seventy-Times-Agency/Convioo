/** Saved + scheduled searches. */

import type { SearchScope } from "../api";
import { request } from "./_core";

export type SavedSearchSchedule =
  | "off"
  | "daily"
  | "weekly"
  | "biweekly"
  | "monthly";

export interface SavedSearchRow {
  id: string;
  name: string;
  team_id: string | null;
  niche: string;
  region: string;
  target_languages: string[] | null;
  scope: SearchScope;
  radius_m: number | null;
  max_results: number | null;
  schedule: Exclude<SavedSearchSchedule, "off"> | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_leads_count: number | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export async function listSavedSearches(): Promise<{ items: SavedSearchRow[] }> {
  return request<{ items: SavedSearchRow[] }>("/api/v1/saved-searches");
}

export async function createSavedSearch(args: {
  name: string;
  niche: string;
  region: string;
  scope: SearchScope;
  radius_m?: number | null;
  max_results?: number | null;
  schedule?: SavedSearchSchedule;
  team_id?: string | null;
  target_languages?: string[];
}): Promise<SavedSearchRow> {
  return request<SavedSearchRow>("/api/v1/saved-searches", {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export async function updateSavedSearch(
  id: string,
  args: {
    name?: string;
    schedule?: SavedSearchSchedule;
    active?: boolean;
    max_results?: number | null;
    radius_m?: number | null;
  },
): Promise<SavedSearchRow> {
  return request<SavedSearchRow>(`/api/v1/saved-searches/${id}`, {
    method: "PATCH",
    body: JSON.stringify(args),
  });
}

export async function deleteSavedSearch(id: string): Promise<void> {
  await request<{ ok: boolean }>(`/api/v1/saved-searches/${id}`, {
    method: "DELETE",
  });
}

export async function runSavedSearchNow(
  id: string,
): Promise<{ id: string; queued: boolean }> {
  return request<{ id: string; queued: boolean }>(
    `/api/v1/saved-searches/${id}/run`,
    { method: "POST" },
  );
}
