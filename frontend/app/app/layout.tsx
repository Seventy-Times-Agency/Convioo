import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { RequireAuth } from "@/components/RequireAuth";
import { AssistantWidget } from "@/components/AssistantWidget";
import { VerifyEmailBanner } from "@/components/VerifyEmailBanner";

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
          {children}
        </main>
      </div>
      <AssistantWidget />
    </RequireAuth>
  );
}
