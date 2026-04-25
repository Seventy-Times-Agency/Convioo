"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { getMyProfile } from "@/lib/api";
import {
  getCurrentUser,
  setOnboarded,
  type CurrentUser,
} from "@/lib/auth";

/**
 * Client-side gate for the workspace shell.
 *
 * - No user in localStorage → redirect to /login.
 * - User exists but their profile isn't onboarded yet → redirect to
 *   /onboarding so Claude has the personal context the Telegram bot
 *   collects in its 6-step flow.
 *
 * Renders nothing while checks are running so authenticated pages
 * never flash for an unauthenticated visitor.
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
      if (u.onboarded === false) {
        router.replace("/onboarding");
        if (!cancelled) setReady("blocked");
        return;
      }
      // Verify with the backend so a localStorage flag can't outlive
      // the actual profile state (e.g. user reset their profile via the
      // bot then opened the web).
      try {
        const profile = await getMyProfile(u.user_id);
        if (cancelled) return;
        setOnboarded(profile.onboarded);
        if (!profile.onboarded) {
          router.replace("/onboarding");
          setReady("blocked");
          return;
        }
        setReady("ok");
      } catch {
        // Backend hiccup — let the user in; API calls will surface real
        // errors. Better than locking them out on a transient blip.
        if (!cancelled) setReady("ok");
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
