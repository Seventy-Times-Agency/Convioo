"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import { type Lead, leadMarkHex, tempOf } from "@/lib/api";
import { showSuccess } from "@/lib/toast";

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
  const [hovered, setHovered] = useState(false);

  const emailAddress = lead.website_meta?.emails?.[0] ?? null;

  const copyEmail = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!emailAddress) return;
    void navigator.clipboard.writeText(emailAddress).then(() => {
      showSuccess("Email скопирован");
    });
  };

  return (
    <div
      className="card card-hover"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        cursor: "pointer",
        borderLeft: markHex ? `3px solid ${markHex}` : undefined,
        position: "relative",
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
          {(() => {
            const snaps = lead.rating_snapshots;
            if (!snaps || snaps.length < 2) return null;
            const delta = snaps[snaps.length - 1].rating - snaps[snaps.length - 2].rating;
            if (Math.abs(delta) < 0.1) return null;
            return (
              <span
                style={{
                  fontSize: 11,
                  padding: "1px 5px",
                  borderRadius: 4,
                  background: delta > 0 ? "var(--hot)" : "var(--cold)",
                  color: "#fff",
                }}
              >
                {delta > 0 ? `+${delta.toFixed(1)} ▲` : `${delta.toFixed(1)} ▼`}
              </span>
            );
          })()}
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
      {hovered && (
        <div
          style={{
            position: "absolute",
            bottom: 10,
            right: 10,
            display: "flex",
            gap: 6,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClick}
            style={{ fontSize: 11, padding: "3px 8px" }}
          >
            <Icon name="mail" size={11} />
            Написать
          </button>
          {emailAddress && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={copyEmail}
              style={{ fontSize: 11, padding: "3px 8px" }}
              title={emailAddress}
            >
              <Icon name="copy" size={11} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
