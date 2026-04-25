"use client";

import { Icon } from "@/components/Icon";
import { type Lead, leadMarkHex, tempOf } from "@/lib/api";

export function LeadCard({
  lead,
  onClick,
}: {
  lead: Lead;
  onClick?: () => void;
}) {
  const temp = tempOf(lead.score_ai);
  const score = Math.round(lead.score_ai ?? 0);
  const socialCount = lead.social_links
    ? Object.keys(lead.social_links).length
    : 0;
  const markHex = leadMarkHex(lead.mark_color);

  return (
    <div
      className="card card-hover"
      onClick={onClick}
      style={{
        cursor: "pointer",
        borderLeft: markHex ? `3px solid ${markHex}` : undefined,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 12,
        }}
      >
        <div className={"chip chip-" + temp}>
          <span className={"status-dot " + temp} />
          {temp}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 26,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color:
                score >= 75
                  ? "var(--hot)"
                  : score >= 50
                    ? "#B45309"
                    : "var(--cold)",
            }}
          >
            {score}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-dim)" }}>/100</div>
        </div>
      </div>
      <div
        style={{
          fontSize: 15,
          fontWeight: 600,
          marginBottom: 4,
          letterSpacing: "-0.005em",
        }}
      >
        {lead.name}
      </div>
      {(lead.rating ?? null) !== null && (
        <div
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            marginBottom: 10,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Icon name="star" size={12} style={{ color: "var(--warm)" }} />{" "}
          {lead.rating} · {lead.reviews_count ?? 0} reviews
        </div>
      )}
      {lead.summary && (
        <div
          style={{
            fontSize: 13,
            color: "var(--text-muted)",
            lineHeight: 1.5,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            marginBottom: 12,
          }}
        >
          {lead.summary}
        </div>
      )}
      <div className="score-track">
        <div
          className={"score-fill " + temp}
          style={{ width: Math.max(2, score) + "%" }}
        />
      </div>
      <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
        {lead.phone && (
          <span className="chip" style={{ fontSize: 11 }}>
            <Icon name="phone" size={10} />
            phone
          </span>
        )}
        {lead.website && (
          <span className="chip" style={{ fontSize: 11 }}>
            <Icon name="globe" size={10} />
            site
          </span>
        )}
        {socialCount > 0 && (
          <span className="chip" style={{ fontSize: 11 }}>
            <Icon name="users" size={10} />
            {socialCount} social
          </span>
        )}
      </div>
    </div>
  );
}
