/**
 * Client-side auth state. The web user signs up with first + last
 * name only (no password yet); the backend returns a negative bigint
 * user id we persist in localStorage so subsequent API calls scope
 * data to that user. Real session tokens / cookies arrive with the
 * proper auth pass.
 */

const STORAGE_KEY = "leadgen.user";

export interface CurrentUser {
  user_id: number;
  first_name: string;
  last_name: string;
  onboarded?: boolean;
}

export function getCurrentUser(): CurrentUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed.user_id === "number" &&
      typeof parsed.first_name === "string" &&
      typeof parsed.last_name === "string"
    ) {
      return parsed as CurrentUser;
    }
  } catch {
    // fall through
  }
  return null;
}

export function setCurrentUser(user: CurrentUser): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
}

export function setOnboarded(onboarded: boolean): void {
  const u = getCurrentUser();
  if (!u) return;
  setCurrentUser({ ...u, onboarded });
}

export function clearCurrentUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function userInitials(user: CurrentUser): string {
  const f = user.first_name.charAt(0).toUpperCase();
  const l = user.last_name.charAt(0).toUpperCase();
  return (f + l) || "U";
}

export function userFullName(user: CurrentUser): string {
  return `${user.first_name} ${user.last_name}`.trim();
}
