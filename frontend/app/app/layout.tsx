"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { RequireAuth } from "@/components/RequireAuth";
import { AssistantWidget } from "@/components/AssistantWidget";
import { VerifyEmailBanner } from "@/components/VerifyEmailBanner";
import { ProfileNudgeBanner } from "@/components/ProfileNudgeBanner";
import {
  OnboardingTourProvider,
  OnboardingTourTrigger,
  isTourDismissed,
} from "@/components/app/OnboardingTour";
import { fetchAuthMe } from "@/lib/api";
import { useActiveTint } from "@/lib/tint";

/**
 * Shell layout for all authenticated-area pages (/app/*).
 *
 * RequireAuth gates the subtree on a localStorage user record; an
 * unauthenticated visitor is redirected to /login before any of the
 * dashboard / search / CRM pages mount.
 *
 * VerifyEmailBanner sits at the top of the workspace until the
 * email is confirmed (search creation is blocked server-side too).
 *
 * ProfileNudgeBanner gently asks the user to flesh out their profile
 * (or do it with Henry) — it's the path the strict 6-step onboarding
 * used to enforce, only soft and skippable.
 *
 * OnboardingTourProvider wraps the workspace so any /app page can
 * trigger or replay the 4-step product tour. The trigger auto-opens
 * the tour the first time an authenticated user lands inside /app.
 *
 * AssistantWidget mounts here so Henry's floating bubble follows
 * the user across every workspace page.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  const tint = useActiveTint();
  const [shouldOpenTour, setShouldOpenTour] = useState(false);

  useEffect(() => {
    if (isTourDismissed()) return;
    let cancelled = false;
    fetchAuthMe()
      .then((me) => {
        if (cancelled) return;
        if (!me.onboarding_tour_completed) setShouldOpenTour(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <RequireAuth>
      <OnboardingTourProvider>
        <div className="app-layout">
          <Sidebar />
          <main className="main-area" data-tint={tint}>
            <VerifyEmailBanner />
            <ProfileNudgeBanner />
            {children}
          </main>
        </div>
        <AssistantWidget />
        <OnboardingTourTrigger shouldOpen={shouldOpenTour} />
      </OnboardingTourProvider>
    </RequireAuth>
  );
}
