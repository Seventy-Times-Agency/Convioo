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
      } catch {
        // Backend hiccup — let the user in; API calls will surface
        // real errors. Better than locking them out on a transient blip.
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
