"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  type LeadOut,
  type SearchSummary,
  getSearchLeads,
  listSearches,
  readAuth,
} from "@/lib/api";

interface EnrichedLead extends LeadOut {
  searchId: string;
  searchNiche: string;
  searchRegion: string;
}

type Temp = "hot" | "warm" | "cold";

const TEMP_BOUNDS: Record<Temp, [number, number]> = {
  hot: [75, 101],
  warm: [50, 75],
  cold: [0, 50],
};

export default function LeadsPage() {
  const [leads, setLeads] = useState<EnrichedLead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | Temp>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const creds = readAuth();
    if (!creds) return;
    (async () => {
      try {
        const sessions = await listSearches(creds, 50);
        const done = sessions.filter((s) => s.status === "done");
        // Fetch leads for each recent done-session in parallel.
        const batches = await Promise.all(
          done.slice(0, 10).map(async (s: SearchSummary) => {
            try {
              const rows = await getSearchLeads(creds, s.id);
              return rows.map((lead) => ({
                ...lead,
                searchId: s.id,
                searchNiche: s.niche,
                searchRegion: s.region,
              }));
            } catch {
              return [] as EnrichedLead[];
            }
          })
        );
        const flat = batches.flat().sort((a, b) => {
          const sa = a.score_ai ?? -1;
          const sb = b.score_ai ?? -1;
          return sb - sa;
        });
        setLeads(flat);
      } catch (e) {
        const err = e as { detail?: string };
        setError(err.detail ?? "Failed to load leads.");
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    if (!leads) return [];
    const q = search.trim().toLowerCase();
    return leads.filter((l) => {
      if (filter !== "all") {
        const [lo, hi] = TEMP_BOUNDS[filter];
        const s = l.score_ai ?? -1;
        if (s < lo || s >= hi) return false;
      }
      if (!q) return true;
      return (
        l.name.toLowerCase().includes(q) ||
        (l.category ?? "").toLowerCase().includes(q) ||
        (l.address ?? "").toLowerCase().includes(q) ||
        l.searchNiche.toLowerCase().includes(q) ||
        l.searchRegion.toLowerCase().includes(q)
      );
    });
  }, [leads, filter, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <header
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: 16,
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Lead base
          </div>
          <h1
            style={{
              fontSize: 30,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              margin: 0,
            }}
          >
            Every lead you've collected.
          </h1>
          <p
            style={{
              fontSize: 14,
              color: "var(--text-muted)",
              margin: "6px 0 0",
            }}
          >
            Aggregated across your recent sessions. Sort by score, filter by
            temperature, search any field.
          </p>
        </div>
        <Link href="/app/search" className="btn">
          + New search
        </Link>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: 12,
          alignItems: "center",
        }}
      >
        <input
          className="input"
          placeholder="Search by name, category, address, niche, region…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div style={{ display: "flex", gap: 6 }}>
          {(["all", "hot", "warm", "cold"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setFilter(t)}
              className={filter === t ? "btn btn-sm" : "btn btn-ghost btn-sm"}
              style={{ textTransform: "capitalize" }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div
          className="card"
          style={{ borderColor: "var(--cold)", color: "var(--cold)" }}
        >
          {error}
        </div>
      )}

      {!error && leads == null && (
        <div className="card">
          <div
            className="skeleton"
            style={{ width: "60%", height: 14, marginBottom: 10 }}
          />
          <div className="skeleton" style={{ width: "40%", height: 12 }} />
        </div>
      )}

      {leads && leads.length === 0 && !error && (
        <div
          className="card"
          style={{ padding: 48, textAlign: "center", color: "var(--text-muted)" }}
        >
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              marginBottom: 8,
              color: "var(--text)",
            }}
          >
            No leads yet.
          </div>
          Run a search — the leads will show up here.
        </div>
      )}

      {filtered.length > 0 && (
        <div
          className="card"
          style={{ padding: 0, overflow: "hidden" }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr 130px 140px 180px",
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
            <span></span>
            <span>Company</span>
            <span>Score</span>
            <span>Rating</span>
            <span>Session</span>
          </div>
          {filtered.map((lead) => (
            <LeadRow key={lead.id} lead={lead} />
          ))}
        </div>
      )}

      {leads && leads.length > 0 && (
        <div
          style={{
            fontSize: 12,
            color: "var(--text-dim)",
            textAlign: "right",
          }}
        >
          Showing {filtered.length} of {leads.length} leads
        </div>
      )}
    </div>
  );
}

function LeadRow({ lead }: { lead: EnrichedLead }) {
  const temp: Temp =
    lead.score_ai != null && lead.score_ai >= 75
      ? "hot"
      : lead.score_ai != null && lead.score_ai >= 50
        ? "warm"
        : "cold";
  return (
    <Link
      href={`/app/searches/${lead.searchId}`}
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr 130px 140px 180px",
        gap: 12,
        padding: "14px 20px",
        borderTop: "1px solid var(--border)",
        alignItems: "center",
        fontSize: 14,
        transition: "background 0.12s",
      }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.background = "var(--surface-2)")
      }
      onMouseLeave={(e) =>
        (e.currentTarget.style.background = "transparent")
      }
    >
      <span className={`status-dot ${temp}`} />
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontWeight: 600,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {lead.name}
        </div>
        <div
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {lead.category ?? "—"}
          {lead.address ? ` · ${lead.address}` : ""}
        </div>
      </div>
      <div
        className="mono"
        style={{
          fontWeight: 600,
          color:
            temp === "hot"
              ? "var(--hot)"
              : temp === "warm"
                ? "#b45309"
                : "var(--cold)",
        }}
      >
        {lead.score_ai != null ? Math.round(lead.score_ai) : "—"}
      </div>
      <div style={{ color: "var(--text-muted)" }}>
        {lead.rating != null ? `★ ${lead.rating}` : "—"}
        {lead.reviews_count ? ` (${lead.reviews_count})` : ""}
      </div>
      <div
        style={{
          fontSize: 12,
          color: "var(--text-muted)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        title={`${lead.searchNiche} · ${lead.searchRegion}`}
      >
        {lead.searchNiche} · {lead.searchRegion}
      </div>
    </Link>
  );
}

