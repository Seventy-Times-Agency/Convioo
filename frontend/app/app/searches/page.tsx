"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SearchStatusPill } from "@/components/SearchStatusPill";
import { type SearchSummary, listSearches, readAuth } from "@/lib/api";
import { formatDuration, formatRelative } from "@/lib/format";

export default function SearchesPage() {
  const [searches, setSearches] = useState<SearchSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const creds = readAuth();
    if (!creds) return;
    listSearches(creds, 100)
      .then(setSearches)
      .catch((e: { detail?: string; status?: number }) => {
        const prefix =
          e.status === 0
            ? "Backend unreachable"
            : e.status
              ? `Backend error ${e.status}`
              : "Failed to load searches";
        setError(`${prefix}: ${e.detail ?? "unknown"}`);
      });
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Sessions
          </div>
          <h1
            style={{
              fontSize: 32,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              margin: 0,
            }}
          >
            All searches
          </h1>
        </div>
        <Link href="/app/search" className="btn">
          + New search
        </Link>
      </header>

      {error && (
        <div
          className="card"
          style={{ borderColor: "var(--cold)", color: "var(--cold)" }}
        >
          {error}
        </div>
      )}

      {!error && searches == null && (
        <div className="card">
          <div className="skeleton" style={{ width: "60%", height: 16, marginBottom: 12 }} />
          <div className="skeleton" style={{ width: "40%", height: 12 }} />
        </div>
      )}

      {searches && searches.length === 0 && (
        <div className="card" style={{ padding: 32, textAlign: "center" }}>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>
            No searches yet.
          </div>
          <div
            style={{
              fontSize: 14,
              color: "var(--text-muted)",
              marginBottom: 16,
            }}
          >
            Run your first one — it takes about a minute.
          </div>
          <Link href="/app/search" className="btn">
            Start a search →
          </Link>
        </div>
      )}

      {searches && searches.length > 0 && (
        <div
          className="card"
          style={{ padding: 0, overflow: "hidden" }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.4fr 1fr 110px 110px 110px 120px",
              gap: 12,
              padding: "14px 20px",
              borderBottom: "1px solid var(--border)",
              fontSize: 11,
              fontWeight: 600,
              color: "var(--text-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            <span>Niche</span>
            <span>Region</span>
            <span>Created</span>
            <span>Duration</span>
            <span>Hot</span>
            <span>Status</span>
          </div>
          {searches.map((s) => (
            <Link
              key={s.id}
              href={`/app/searches/${s.id}`}
              style={{
                display: "grid",
                gridTemplateColumns: "1.4fr 1fr 110px 110px 110px 120px",
                gap: 12,
                padding: "16px 20px",
                borderTop: "1px solid var(--border)",
                fontSize: 14,
                alignItems: "center",
                background: "transparent",
                transition: "background 0.12s",
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = "var(--surface-2)")
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = "transparent")
              }
            >
              <div>
                <div style={{ fontWeight: 600 }}>{s.niche}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  {s.leads_count} leads
                </div>
              </div>
              <div style={{ color: "var(--text-muted)" }}>{s.region}</div>
              <div style={{ color: "var(--text-muted)" }}>
                {formatRelative(s.created_at)}
              </div>
              <div className="mono" style={{ color: "var(--text-muted)" }}>
                {formatDuration(s.created_at, s.finished_at)}
              </div>
              <div
                className="mono"
                style={{
                  fontWeight: 600,
                  color: (s.hot_leads_count ?? 0) > 0 ? "var(--hot)" : "var(--text-muted)",
                }}
              >
                {s.hot_leads_count ?? 0}
              </div>
              <div>
                <SearchStatusPill status={s.status} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
