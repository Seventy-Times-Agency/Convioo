import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { RequireAuth } from "@/components/RequireAuth";

/**
 * Shell layout for all authenticated-area pages (/app/*).
 *
 * RequireAuth gates the subtree on a localStorage user record; an
 * unauthenticated visitor is redirected to /login before any of the
 * dashboard / search / CRM pages mount.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <div className="app-layout">
        <Sidebar />
        <main className="main-area">{children}</main>
      </div>
    </RequireAuth>
  );
}
