/**
 * Client-side auth state.
 *
 * The web user registers with email + password + first/last name.
 * After register/login the backend returns the auth payload which we
 * persist in localStorage so subsequent API calls know who's
 * speaking and what their workspace flags are. A proper httpOnly
 * cookie session lands once we move past the open-demo deploy.
 */

const STORAGE_KEY = "convioo.user";
const LEGACY_STORAGE_KEY = "leadgen.user";

export interface CurrentUser {
  user_id: number;
  first_name: string;
  last_name: string;
  email?: string | null;
  email_verified?: boolean;
  onboarded?: boolean;
}

export function getCurrentUser(): CurrentUser | null {
  if (typeof window === "undefined") return null;
  let raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    // One-time migration: pick up the legacy key if present.
    raw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (raw) {
      window.localStorage.setItem(STORAGE_KEY, raw);
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    }
  }
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

export function setEmailVerified(verified: boolean): void {
  const u = getCurrentUser();
  if (!u) return;
  setCurrentUser({ ...u, email_verified: verified });
}

export function clearCurrentUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_STORAGE_KEY);
}

export function userInitials(user: CurrentUser): string {
  const f = user.first_name.charAt(0).toUpperCase();
  const l = user.last_name.charAt(0).toUpperCase();
  return (f + l) || "U";
}

export function userFullName(user: CurrentUser): string {
  return `${user.first_name} ${user.last_name}`.trim();
}
