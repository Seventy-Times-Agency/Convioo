"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import {
  type Lead,
  type LeadMarkColor,
  type LeadStatus,
  LEAD_MARK_COLORS,
  LEAD_MARK_HEX,
  leadMarkHex,
  setLeadMark,
  tempOf,
  updateLead,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const STATUSES: LeadStatus[] = ["new", "contacted", "replied", "won", "archived"];

export function LeadDetailModal({
  lead,
  onClose,
  onUpdated,
}: {
  lead: Lead;
  onClose: () => void;
  onUpdated?: (updated: Lead) => void;
}) {
  const { t } = useLocale();
  const [status, setStatus] = useState<LeadStatus>(lead.lead_status);
  const [note, setNote] = useState(lead.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [markColor, setMarkColor] = useState<string | null>(lead.mark_color);
  const [markBusy, setMarkBusy] = useState(false);

  const pickColor = async (color: LeadMarkColor | null) => {
    setMarkBusy(true);
    setError(null);
    const previous = markColor;
    setMarkColor(color);
    try {
      const updated = await setLeadMark(lead.id, color);
      onUpdated?.(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setMarkColor(previous);
    } finally {
      setMarkBusy(false);
    }
  };

  const temp = tempOf(lead.score_ai);
  const score = Math.round(lead.score_ai ?? 0);
  const strengths = lead.strengths ?? [];
  const weaknesses = lead.weaknesses ?? [];
  const redFlags = lead.red_flags ?? [];
  const socialLinks = lead.social_links ?? {};

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateLead(lead.id, {
        lead_status: status,
        notes: note,
      });
      onUpdated?.(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,15,20,0.4)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 30,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          borderRadius: 16,
          width: "100%",
          maxWidth: 880,
          maxHeight: "90vh",
          overflow: "auto",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        <div
          style={{
            padding: "24px 28px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            position: "sticky",
            top: 0,
            background: "var(--surface)",
            zIndex: 2,
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div className={"chip chip-" + temp}>
                <span className={"status-dot " + temp} />
                {temp}
              </div>
              {lead.category && (
                <span className="chip">{lead.category}</span>
              )}
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              {markColor && (
                <span
                  title={t("lead.mark.title")}
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    background: leadMarkHex(markColor) ?? "var(--text-dim)",
                    flexShrink: 0,
                  }}
                />
              )}
              <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.02em" }}>
                {lead.name}
              </div>
            </div>
            {lead.address && (
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
                {lead.address}
              </div>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ textAlign: "right" }}>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 36,
                  fontWeight: 700,
                  color:
                    score >= 75
                      ? "var(--hot)"
                      : score >= 50
                        ? "#B45309"
                        : "var(--cold)",
                  letterSpacing: "-0.02em",
                }}
              >
                {score}
              </div>
              <div className="eyebrow" style={{ fontSize: 10 }}>AI score</div>
            </div>
            <button className="btn-icon" onClick={onClose} type="button">
              <Icon name="x" size={18} />
            </button>
          </div>
        </div>

        <div
          style={{
            padding: "24px 28px",
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr",
            gap: 28,
          }}
        >
          <div>
            {lead.advice && (
              <div
                className="card"
                style={{
                  padding: 20,
                  background: "var(--accent-soft)",
                  border: "1px solid color-mix(in srgb, var(--accent) 20%, transparent)",
                  marginBottom: 18,
                }}
              >
                <div
                  className="eyebrow"
                  style={{ color: "var(--accent)", marginBottom: 8 }}
                >
                  <Icon
                    name="sparkles"
                    size={11}
                    style={{ marginRight: 4, verticalAlign: "-2px" }}
                  />
                  {t("lead.howToPitch")}
                </div>
                <div style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text)" }}>
                  {lead.advice}
                </div>
                <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled
                    title={t("lead.sendEmail.soon")}
                    style={{ opacity: 0.65 }}
                  >
                    <Icon name="mail" size={13} />
                    {t("lead.sendEmail.gmail")}
                    <span
                      className="chip"
                      style={{
                        fontSize: 9,
                        marginLeft: 6,
                        padding: "1px 6px",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        color: "var(--text-dim)",
                      }}
                    >
                      {t("settings.connector.soon")}
                    </span>
                  </button>
                </div>
              </div>
            )}

            {(strengths.length > 0 || weaknesses.length > 0) && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 14,
                  marginBottom: 18,
                }}
              >
                <div>
                  <div className="eyebrow" style={{ marginBottom: 8, color: "var(--hot)" }}>
                    {t("lead.strengths")}
                  </div>
                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: 18,
                      fontSize: 13.5,
                      lineHeight: 1.65,
                      color: "var(--text)",
                    }}
                  >
                    {strengths.map((s, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="eyebrow" style={{ marginBottom: 8, color: "#B45309" }}>
                    {t("lead.weaknesses")}
                  </div>
                  <ul
                    style={{
                      margin: 0,
                      paddingLeft: 18,
                      fontSize: 13.5,
                      lineHeight: 1.65,
                      color: "var(--text)",
                    }}
                  >
                    {weaknesses.map((s, i) => (
                      <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {redFlags.length > 0 && (
              <div
                style={{
                  padding: 14,
                  background: "color-mix(in srgb, var(--cold) 5%, transparent)",
                  border: "1px solid color-mix(in srgb, var(--cold) 20%, transparent)",
                  borderRadius: 10,
                  marginBottom: 18,
                }}
              >
                <div className="eyebrow" style={{ color: "var(--cold)", marginBottom: 6 }}>
                  {t("lead.redFlags")}
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: 18,
                    fontSize: 13,
                    color: "var(--text-muted)",
                  }}
                >
                  {redFlags.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>{t("lead.notes")}</div>
              <textarea
                className="textarea"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("lead.notesPh")}
                rows={3}
              />
            </div>
          </div>

          <div>
            <div className="card" style={{ padding: 18, marginBottom: 14 }}>
              <div
                className="eyebrow"
                style={{
                  marginBottom: 10,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span>{t("lead.mark.title")}</span>
                {markColor && (
                  <button
                    type="button"
                    onClick={() => pickColor(null)}
                    disabled={markBusy}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: "var(--text-dim)",
                      fontSize: 11,
                      padding: 0,
                    }}
                  >
                    {t("lead.mark.clear")}
                  </button>
                )}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {LEAD_MARK_COLORS.map((c) => {
                  const active = markColor === c;
                  return (
                    <button
                      key={c}
                      type="button"
                      onClick={() => pickColor(active ? null : c)}
                      disabled={markBusy}
                      title={c}
                      aria-label={c}
                      style={{
                        width: 26,
                        height: 26,
                        borderRadius: "50%",
                        background: LEAD_MARK_HEX[c],
                        border: active
                          ? "2px solid var(--text)"
                          : "2px solid transparent",
                        boxShadow: active
                          ? "0 0 0 1px var(--surface) inset"
                          : "none",
                        cursor: markBusy ? "wait" : "pointer",
                      }}
                    />
                  );
                })}
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-dim)",
                  marginTop: 8,
                  lineHeight: 1.45,
                }}
              >
                {t("lead.mark.help")}
              </div>
            </div>

            <div className="card" style={{ padding: 18, marginBottom: 14 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>{t("lead.status")}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {STATUSES.map((s) => (
                  <div
                    key={s}
                    onClick={() => setStatus(s)}
                    style={{
                      padding: "9px 12px",
                      borderRadius: 8,
                      cursor: "pointer",
                      fontSize: 13,
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      background: status === s ? "var(--accent-soft)" : "transparent",
                      color: status === s ? "var(--accent)" : "var(--text-muted)",
                      fontWeight: status === s ? 600 : 500,
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: status === s ? "var(--accent)" : "var(--border-strong)",
                      }}
                    />
                    {t(`lead.statusLabel.${s}` as TranslationKey)}
                  </div>
                ))}
              </div>
            </div>

            <div className="card" style={{ padding: 18 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>{t("lead.contact")}</div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                  fontSize: 13,
                }}
              >
                {lead.phone && (
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Icon name="phone" size={14} style={{ color: "var(--text-muted)" }} />
                    {lead.phone}
                  </div>
                )}
                {lead.website && (
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Icon name="globe" size={14} style={{ color: "var(--text-muted)" }} />
                    <a
                      href={lead.website.startsWith("http") ? lead.website : `https://${lead.website}`}
                      target="_blank"
                      rel="noreferrer noopener"
                      style={{ color: "var(--accent)" }}
                    >
                      {lead.website}
                    </a>
                  </div>
                )}
                {lead.address && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      color: "var(--text-muted)",
                    }}
                  >
                    <Icon name="mapPin" size={14} />
                    {lead.address}
                  </div>
                )}
                {Object.keys(socialLinks).length > 0 && (
                  <div
                    style={{
                      borderTop: "1px solid var(--border)",
                      paddingTop: 10,
                      marginTop: 4,
                      display: "flex",
                      gap: 6,
                      flexWrap: "wrap",
                    }}
                  >
                    {Object.entries(socialLinks).map(([k, v]) => (
                      <span key={k} className="chip" style={{ fontSize: 11 }}>
                        {k}: {v}
                      </span>
                    ))}
                  </div>
                )}
                {lead.rating !== null && (
                  <div
                    style={{
                      borderTop: "1px solid var(--border)",
                      paddingTop: 10,
                      marginTop: 4,
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                    }}
                  >
                    <Icon name="star" size={14} style={{ color: "var(--warm)" }} />
                    <b>{lead.rating}</b> · {lead.reviews_count ?? 0} {t("lead.rating")}
                  </div>
                )}
              </div>
            </div>

            {error && (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--cold)",
                  marginTop: 10,
                }}
              >
                {error}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
              <button
                className="btn"
                style={{ flex: 1, justifyContent: "center" }}
                disabled={saving}
                onClick={save}
                type="button"
              >
                {saving ? t("common.saving") : t("common.save")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
