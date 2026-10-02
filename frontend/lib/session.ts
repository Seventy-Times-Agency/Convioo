/**
 * Выход из аккаунта — одна функция на все кнопки «Выйти».
 *
 * Раньше чистился только localStorage, а httpOnly-cookie оставалась
 * живой: на общем компьютере сессия переживала выход. Теперь сначала
 * гасим сессию на сервере, потом чистим локальное зеркало — вместе с
 * историей Henry, чтобы следующий человек в этом браузере не читал
 * чужую переписку.
 */

import { logoutCurrentSession } from "@/lib/api";
import { clearCurrentUser } from "@/lib/auth";
import { clearActiveWorkspace } from "@/lib/workspace";

const HENRY_HISTORY_PREFIX = "convioo.henry.history";

export function clearHenryHistory(): void {
  if (typeof window === "undefined") return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const k = window.localStorage.key(i);
      if (k && k.startsWith(HENRY_HISTORY_PREFIX)) keys.push(k);
    }
    keys.forEach((k) => window.localStorage.removeItem(k));
  } catch {
    // storage disabled — nothing to clear
  }
}

export async function logout(): Promise<void> {
  try {
    await logoutCurrentSession();
  } catch {
    // Сессии уже нет или сеть упала — локально всё равно выходим.
  }
  clearCurrentUser();
  clearActiveWorkspace();
  clearHenryHistory();
}
