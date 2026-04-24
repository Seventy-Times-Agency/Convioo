"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { type AuthCreds, readAuth } from "@/lib/api";

export default function TeamPage() {
  const [creds, setCreds] = useState<AuthCreds | null>(null);

  useEffect(() => {
    setCreds(readAuth());
  }, []);

  const initials = (creds?.displayName ?? "U").slice(0, 2).toUpperCase();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <header>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          Team
        </div>
        <h1
          style={{
            fontSize: 30,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            margin: 0,
          }}
        >
          Your workspace members.
        </h1>
        <p
          style={{
            fontSize: 14,
            color: "var(--text-muted)",
            margin: "6px 0 0",
          }}
        >
          Right now every name is its own workspace. Shared team quotas and
          per-seat roles land once the invite flow is wired up.
        </p>
      </header>

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "auto 1fr auto auto",
            gap: 16,
            padding: "18px 20px",
            alignItems: "center",
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: "var(--accent)",
              color: "white",
              display: "grid",
              placeItems: "center",
              fontSize: 14,
              fontWeight: 700,
            }}
          >
            {initials}
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>
              {creds?.displayName ?? "—"}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              id {creds?.userId ?? "—"}
            </div>
          </div>
          <span className="chip chip-accent">Owner</span>
          <span
            style={{
              fontSize: 12,
              color: "var(--text-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            }}
          >
            You
          </span>
        </div>
      </div>

      <div
        className="card"
        style={{
          padding: 28,
          background:
            "linear-gradient(135deg, var(--surface), var(--surface-2))",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div className="mesh-bg" style={{ opacity: 0.35 }} />
        <div style={{ position: "relative" }}>
          <div className="eyebrow" style={{ marginBottom: 10 }}>
            Next up
          </div>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
            Invite a teammate
          </div>
          <p
            style={{
              fontSize: 14,
              color: "var(--text-muted)",
              lineHeight: 1.55,
              margin: "0 0 16px",
              maxWidth: 520,
            }}
          >
            Invites, role assignment (owner / member / viewer) and a shared
            quota bucket are queued for the next iteration. The backend
            models are already in place (Team / TeamMembership) — the UI to
            drive them is the last step.
          </p>
          <Link href="/app/search" className="btn">
            Run a search instead →
          </Link>
        </div>
      </div>
    </div>
  );
}
