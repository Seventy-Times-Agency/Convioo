import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { RequireAuth } from "@/components/RequireAuth";
import { AssistantWidget } from "@/components/AssistantWidget";
import { VerifyEmailBanner } from "@/components/VerifyEmailBanner";
import { ProfileNudgeBanner } from "@/components/ProfileNudgeBanner";

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
 * AssistantWidget mounts here so Henry's floating bubble follows
 * the user across every workspace page.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <div className="app-layout">
        <Sidebar />
        <main className="main-area">
          <VerifyEmailBanner />
          <ProfileNudgeBanner />
          {children}
        </main>
      </div>
      <AssistantWidget />
    </RequireAuth>
  );
}
