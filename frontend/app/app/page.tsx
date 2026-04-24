"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SearchStatusPill } from "@/components/SearchStatusPill";
import { type SearchSummary, listSearches, readAuth } from "@/lib/api";
import { formatRelative } from "@/lib/format";

export default function DashboardPage() {
  const [searches, setSearches] = useState<SearchSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string>("");

  useEffect(() => {
    const creds = readAuth();
    if (!creds) return;
    setDisplayName(creds.displayName);
    listSearches(creds, 10)
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

  const list = searches ?? [];
  const running = list.filter((s) => s.status === "running" || s.status === "pending");
  const done = list.filter((s) => s.status === "done");
  const totalLeads = done.reduce((a, s) => a + (s.leads_count ?? 0), 0);
  const hot = done.reduce((a, s) => a + (s.hot_leads_count ?? 0), 0);
  const avgScore =
    done.filter((s) => s.avg_score != null).length === 0
      ? null
      : Math.round(
          done
            .filter((s) => s.avg_score != null)
            .reduce((a, s) => a + (s.avg_score ?? 0), 0) /
            done.filter((s) => s.avg_score != null).length
        );

  const greeting =
    new Date().getHours() < 12 ? "Good morning" : "Good afternoon";

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
          <h1
            style={{
              fontSize: 30,
              fontWeight: 700,
              letterSpacing: "-0.025em",
              margin: 0,
            }}
          >
            {greeting}
            {displayName ? `, ${displayName}` : ""}.
          </h1>
          <p
            style={{
              fontSize: 14,
              color: "var(--text-muted)",
              margin: "6px 0 0",
            }}
          >
            Here's what's happening in your workspace.
          </p>
        </div>
        <Link href="/app/search" className="btn">
          + New search
        </Link>
      </header>

      {/* Hero KPI strip with mesh backdrop */}
      <div
        style={{
          position: "relative",
          padding: "32px 28px",
          borderRadius: 16,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          overflow: "hidden",
        }}
      >
        <div className="mesh-bg" style={{ opacity: 0.4 }} />
        <div
          style={{
            position: "relative",
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 20,
          }}
        >
          <HeroKpi
            n={list.length}
            label="Sessions run"
            sub={
              running.length > 0
                ? `${running.length} active now`
                : "none active"
            }
            loading={searches == null}
          />
          <HeroKpi
            n={totalLeads}
            label="Leads analyzed"
            sub="across all sessions"
            loading={searches == null}
          />
          <HeroKpi
            n={hot}
            label="Hot leads"
            sub="ready for outreach"
            accent="var(--hot)"
            loading={searches == null}
          />
          <HeroKpi
            n={avgScore != null ? `${avgScore}/100` : "—"}
            label="Avg AI score"
            sub="enriched leads"
            accent="var(--accent)"
            loading={searches == null}
          />
        </div>
      </div>

      {/* Recent sessions + quick actions */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.6fr 1fr",
          gap: 20,
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 14,
            }}
          >
            <div>
              <div className="eyebrow">Recent sessions</div>
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 600,
                  letterSpacing: "-0.01em",
                  marginTop: 4,
                }}
              >
                Your searches
              </div>
            </div>
            <Link
              href="/app/searches"
              style={{ fontSize: 13, color: "var(--accent)" }}
            >
              View all →
            </Link>
          </div>

          {error && (
            <div
              className="card"
              style={{ borderColor: "var(--cold)", color: "var(--cold)" }}
            >
              {error}
            </div>
          )}

          {!error && searches == null && (
            <div
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              {[0, 1, 2].map((i) => (
                <div key={i} className="card" style={{ padding: "16px 20px" }}>
                  <div
                    className="skeleton"
                    style={{
                      width: "60%",
                      height: 14,
                      marginBottom: 8,
                    }}
                  />
                  <div
                    className="skeleton"
                    style={{ width: "35%", height: 12 }}
                  />
                </div>
              ))}
            </div>
          )}

          {searches && searches.length === 0 && <EmptyState />}

          {searches && searches.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {searches.slice(0, 5).map((s) => (
                <SessionRow key={s.id} session={s} />
              ))}
            </div>
          )}
        </div>

        <div>
          <div style={{ marginBottom: 14 }}>
            <div className="eyebrow">Start now</div>
            <div
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: "-0.01em",
                marginTop: 4,
              }}
            >
              Quick actions
            </div>
          </div>
          <Link
            href="/app/search"
            className="card card-hover"
            style={{
              display: "block",
              background:
                "linear-gradient(135deg, var(--surface), var(--surface-2))",
            }}
          >
            <div
              style={{
                fontSize: 16,
                fontWeight: 600,
                marginBottom: 6,
                color: "var(--accent)",
              }}
            >
              ✦ Launch a new search
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Describe your target niche and region. The AI will handle the
              rest.
            </div>
          </Link>
          <Link
            href="/app/searches"
            className="card card-hover"
            style={{ display: "block", marginTop: 10 }}
          >
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>
              Browse all sessions
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Search, filter and open every lead you've collected.
            </div>
          </Link>
          <Link
            href="/app/profile"
            className="card card-hover"
            style={{
              display: "block",
              marginTop: 10,
              background: "var(--surface-2)",
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
              Tune what you sell
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Set your profession so the AI scores leads against your actual
              offer.
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}

function HeroKpi({
  n,
  label,
  sub,
  accent,
  loading,
}: {
  n: number | string;
  label: string;
  sub: string;
  accent?: string;
  loading?: boolean;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 44,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          color: accent ?? "var(--text)",
          minHeight: 52,
        }}
      >
        {loading ? (
          <span className="skeleton" style={{ width: 70, height: 38 }} />
        ) : (
          n
        )}
      </div>
      <div className="eyebrow" style={{ marginTop: 4 }}>
        {label}
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          marginTop: 4,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function SessionRow({ session }: { session: SearchSummary }) {
  const isActive =
    session.status === "running" || session.status === "pending";
  const dotClass = isActive
    ? "live"
    : session.status === "done"
      ? "hot"
      : "cold";
  return (
    <Link
      href={`/app/searches/${session.id}`}
      className="card card-hover"
      style={{ display: "block", padding: "16px 20px" }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto auto auto",
          gap: 20,
          alignItems: "center",
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginBottom: 4,
            }}
          >
            <span className={`status-dot ${dotClass}`} />
            <div style={{ fontSize: 15, fontWeight: 600 }}>{session.niche}</div>
            <span className="chip" style={{ fontSize: 11 }}>
              {session.region}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {isActive
              ? "Running…"
              : `${session.leads_count} leads · ${session.hot_leads_count ?? 0} hot · ${formatRelative(session.created_at)}`}
          </div>
        </div>
        {!isActive && (
          <>
            <div style={{ textAlign: "right" }}>
              <div
                className="mono"
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: "var(--hot)",
                }}
              >
                {session.hot_leads_count ?? 0}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: "var(--text-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                }}
              >
                hot
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div
                className="mono"
                style={{ fontSize: 18, fontWeight: 700 }}
              >
                {session.leads_count}
              </div>
              <div
                style={{
                  fontSize: 10,
                  color: "var(--text-dim)",
                  textTransform: "uppercase",
                  letterSpacing: "0.12em",
                }}
              >
                total
              </div>
            </div>
          </>
        )}
        <SearchStatusPill status={session.status} />
      </div>
    </Link>
  );
}

function EmptyState() {
  return (
    <div
      className="card"
      style={{
        padding: 48,
        textAlign: "center",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div className="mesh-bg" style={{ opacity: 0.6 }} />
      <div style={{ position: "relative" }}>
        <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
          No searches yet.
        </div>
        <div
          style={{
            fontSize: 14,
            color: "var(--text-muted)",
            marginBottom: 20,
          }}
        >
          Run your first one — it takes about a minute.
        </div>
        <Link href="/app/search" className="btn">
          Start a search →
        </Link>
      </div>
    </div>
  );
}
