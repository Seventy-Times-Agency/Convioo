/**
 * Active workspace selector. Persists which "lens" the user is
 * working in: their personal pool ({ kind: "personal" }) or one of
 * the teams they belong to ({ kind: "team", team_id, team_name }).
 *
 * Every list endpoint reads this on render so the sidebar nav and
 * the data on screen always agree. ``setActiveWorkspace`` emits a
 * "leadgen.workspace" custom event so UI subscribed to the value
 * (sidebar, dashboard, CRM) can re-render without a full reload.
 */

const STORAGE_KEY = "leadgen.workspace";
const EVENT_NAME = "leadgen.workspace";

export type Workspace =
  | { kind: "personal" }
  | { kind: "team"; team_id: string; team_name: string };

export const PERSONAL_WORKSPACE: Workspace = { kind: "personal" };

export function getActiveWorkspace(): Workspace {
  if (typeof window === "undefined") return PERSONAL_WORKSPACE;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return PERSONAL_WORKSPACE;
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.kind === "team" && typeof parsed.team_id === "string") {
      return {
        kind: "team",
        team_id: parsed.team_id,
        team_name: typeof parsed.team_name === "string" ? parsed.team_name : "",
      };
    }
  } catch {
    // fall through to personal
  }
  return PERSONAL_WORKSPACE;
}

export function setActiveWorkspace(workspace: Workspace): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
  window.dispatchEvent(new CustomEvent(EVENT_NAME));
}

export function clearActiveWorkspace(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new CustomEvent(EVENT_NAME));
}

export function activeTeamId(): string | undefined {
  const w = getActiveWorkspace();
  return w.kind === "team" ? w.team_id : undefined;
}

export function subscribeWorkspace(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => listener();
  window.addEventListener(EVENT_NAME, handler);
  // Cross-tab updates: localStorage events fire in *other* tabs only.
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEY) listener();
  });
  return () => {
    window.removeEventListener(EVENT_NAME, handler);
  };
}
