"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { type AuthCreds, clearAuth } from "@/lib/api";

const NAV: { href: string; label: string; group?: string }[] = [
  { href: "/app", label: "Dashboard", group: "Workspace" },
  { href: "/app/search", label: "New search", group: "Workspace" },
  { href: "/app/searches", label: "All sessions", group: "Workspace" },
  { href: "/app/leads", label: "Lead base", group: "Workspace" },
  { href: "/app/profile", label: "Profile", group: "Account" },
  { href: "/app/team", label: "Team", group: "Account" },
  { href: "/app/settings", label: "Settings", group: "Account" },
];

/**
 * Two-column app frame: sidebar with branding + nav on the left, main
 * content on the right. Sticky sidebar keeps the brand+nav visible
 * during long scrolls (sessions list, lead tables).
 */
export function AppShell({
  creds,
  children,
}: {
  creds: AuthCreds;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const router = useRouter();

  const initials = (creds.displayName ?? `U${creds.userId}`)
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/app" className="sidebar-logo">
          <span className="sidebar-logo-mark">L</span>
          <span>Leadgen</span>
        </Link>

        <nav style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {["Workspace", "Account"].map((group) => (
            <div
              key={group}
              style={{ display: "flex", flexDirection: "column", gap: 2 }}
            >
              <div
                className="eyebrow"
                style={{ padding: "4px 12px", fontSize: 10 }}
              >
                {group}
              </div>
              {NAV.filter((item) => item.group === group).map((item) => {
                const active =
                  item.href === "/app"
                    ? pathname === "/app"
                    : pathname.startsWith(item.href);
                return (
                  <Link key={item.href} href={item.href} data-active={active}>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div style={{ marginTop: "auto" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 12px",
              borderRadius: 10,
              background: "var(--surface-2)",
              fontSize: 13,
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 8,
                background: "var(--accent)",
                color: "white",
                display: "grid",
                placeItems: "center",
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              {initials}
            </div>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {creds.displayName || `User ${creds.userId}`}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                id {creds.userId}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              clearAuth();
              router.replace("/login");
            }}
            className="btn btn-ghost btn-sm"
            style={{ width: "100%", marginTop: 12, justifyContent: "center" }}
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="app-main">{children}</main>
    </div>
  );
}
