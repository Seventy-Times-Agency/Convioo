"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getMyProfile } from "@/lib/api";
import {
  clearCurrentUser,
  getCurrentUser,
  setOnboarded,
  type CurrentUser,
} from "@/lib/auth";
import { clearActiveWorkspace } from "@/lib/workspace";

/**
 * Client-side gate for the workspace shell.
 *
 * Just checks for a signed-in user. The strict 6-step onboarding has
 * been retired — registration now collects only name + age and stamps
 * onboarded_at server-side, so every authenticated user can reach
 * /app immediately. The rest of the profile is filled inside the
 * workspace via the soft profile-nudge banner or with Henry.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState<"loading" | "ok" | "blocked">("loading");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const u: CurrentUser | null = getCurrentUser();
      if (!u) {
        router.replace("/login");
        if (!cancelled) setReady("blocked");
        return;
      }
      try {
        // Resync the local onboarded flag from the backend so a stale
        // localStorage value can't shadow the actual profile state.
        const profile = await getMyProfile(u.user_id);
        if (cancelled) return;
        setOnboarded(profile.onboarded);
        setReady("ok");
      } catch (e) {
        if (cancelled) return;
        // 401 — куки-сессии больше нет (истекла, или пользователя
        // удалили вместе с базой), а localStorage всё ещё помнит
        // аккаунт. Без выхода приложение рисует «залогиненную»
        // оболочку, где каждый запрос падает: пустое меню, «не
        // удалось загрузить» в настройках. Чистим и уводим на вход.
        if (e instanceof ApiError && e.status === 401) {
          clearCurrentUser();
          clearActiveWorkspace();
          router.replace("/login");
          setReady("blocked");
          return;
        }
        // Backend hiccup — let the user in; API calls will surface
        // real errors. Better than locking them out on a transient blip.
        setReady("ok");
      }
    };
    check();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (ready !== "ok") return null;
  return <>{children}</>;
}
