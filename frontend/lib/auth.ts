/**
 * Client-side auth state.
 *
 * The web user registers with email + password + first/last name.
 * After register/login the backend returns the auth payload which we
 * persist in localStorage so subsequent API calls know who's
 * speaking and what their workspace flags are. A proper httpOnly
 * cookie session lands once we move past the open-demo deploy.
 */

import { clearActiveWorkspace } from "@/lib/workspace";

const STORAGE_KEY = "convioo.user";
const LEGACY_STORAGE_KEY = "leadgen.user";

export interface CurrentUser {
  user_id: number;
  first_name: string;
  last_name: string;
  email?: string | null;
  email_verified?: boolean;
  onboarded?: boolean;
  /** Маленькая картинка data:image/…; грузится из профиля. */
  avatar_url?: string | null;
}

const USER_EVENT = "convioo:user";

/** Подписка на смену кэшированного пользователя (аватар, имя). */
export function subscribeCurrentUser(fn: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(USER_EVENT, fn);
  return () => window.removeEventListener(USER_EVENT, fn);
}

export function setCurrentUserAvatar(avatar_url: string | null): void {
  const u = getCurrentUser();
  if (!u || u.avatar_url === avatar_url) return;
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...u, avatar_url }));
  window.dispatchEvent(new Event(USER_EVENT));
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
  // Выбранная команда принадлежит аккаунту, а не браузеру. Войдя под
  // другим пользователем — из демо в свой аккаунт, например, — мы
  // унаследовали бы прошлый выбор: рабочее пространство указывало бы
  // на команду, где новый пользователь не состоит, и главная падала
  // бы с "not a team member", а меню схлопывалось до пары разделов.
  // Сбрасываем здесь, а не на каждом экране входа: точек, меняющих
  // пользователя, шесть, и любую новую легко забыть.
  const previous = getCurrentUser();
  if (!previous || previous.user_id !== user.user_id) {
    clearActiveWorkspace();
  }
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
