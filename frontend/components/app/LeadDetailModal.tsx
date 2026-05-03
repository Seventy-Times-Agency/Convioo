"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { LeadDetailExtras } from "@/components/app/LeadDetailExtras";
import {
  type EmailTone,
  type Lead,
  type LeadEmailDraft,
  type LeadMarkColor,
  type LeadStatus,
  type LeadTag,
  LEAD_MARK_COLORS,
  LEAD_MARK_HEX,
  deleteLead,
  draftLeadEmail,
  leadMarkHex,
  setLeadMark,
  tempOf,
  updateLead,
  getGmailStatus,
  getOutlookStatus,
  sendLeadEmail,
} from "@/lib/api";
import { TagEditor } from "@/components/app/TagEditor";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { useTeamLeadStatuses } from "@/lib/leadStatuses";

const TONES: EmailTone[] = ["professional", "casual", "bold"];

export function LeadDetailModal({
  lead,
  onClose,
  onUpdated,
  onDeleted,
}: {
  lead: Lead;
  onClose: () => void;
  onUpdated?: (updated: Lead) => void;
  onDeleted?: (leadId: string, forever: boolean) => void;
}) {
  const { t } = useLocale();
  const { statuses } = useTeamLeadStatuses();
  const [status, setStatus] = useState<LeadStatus>(lead.lead_status);
  const [note, setNote] = useState(lead.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [markColor, setMarkColor] = useState<string | null>(lead.mark_color);
  const [markBusy, setMarkBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteMenu, setShowDeleteMenu] = useState(false);

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

  const handleDelete = async (forever: boolean) => {
    const confirmText = forever
      ? "Удалить и больше не показывать в будущих поисках?"
      : "Удалить из CRM? (тот же лид может всплыть в новых поисках)";
    if (!window.confirm(confirmText)) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteLead(lead.id, { forever });
      onDeleted?.(lead.id, forever);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
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
                <ColdEmailDraft leadId={lead.id} />
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
              <div className="eyebrow" style={{ marginBottom: 8 }}>Теги</div>
              <TagEditor
                leadId={lead.id}
                initialTags={lead.user_tags ?? []}
                onChanged={(tags) => {
                  // Best-effort sync of the parent's local copy so chips
                  // on the underlying card refresh without a refetch.
                  onUpdated?.({ ...lead, user_tags: tags });
                }}
              />
            </div>

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

            <LeadDetailExtras leadId={lead.id} />
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
                {statuses.map((s) => (
                  <div
                    key={s.id}
                    onClick={() => setStatus(s.key)}
                    style={{
                      padding: "9px 12px",
                      borderRadius: 8,
                      cursor: "pointer",
                      fontSize: 13,
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      background:
                        status === s.key ? "var(--accent-soft)" : "transparent",
                      color:
                        status === s.key ? "var(--accent)" : "var(--text-muted)",
                      fontWeight: status === s.key ? 600 : 500,
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background:
                          status === s.key ? "var(--accent)" : "var(--border-strong)",
                      }}
                    />
                    {s.label}
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

            <div style={{ display: "flex", gap: 8, marginTop: 14, position: "relative" }}>
              <button
                className="btn"
                style={{ flex: 1, justifyContent: "center" }}
                disabled={saving || deleting}
                onClick={save}
                type="button"
              >
                {saving ? t("common.saving") : t("common.save")}
              </button>
              <button
                className="btn btn-ghost"
                style={{ color: "var(--cold)" }}
                disabled={saving || deleting}
                onClick={() => setShowDeleteMenu((v) => !v)}
                type="button"
                aria-haspopup="true"
                aria-expanded={showDeleteMenu}
                title="Удалить"
              >
                <Icon name="trash" size={15} />
              </button>
              {showDeleteMenu && (
                <div
                  style={{
                    position: "absolute",
                    bottom: "calc(100% + 6px)",
                    right: 0,
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    padding: 6,
                    boxShadow: "0 8px 24px rgba(15,15,20,0.12)",
                    minWidth: 260,
                    zIndex: 5,
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                  onMouseLeave={() => setShowDeleteMenu(false)}
                >
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setShowDeleteMenu(false);
                      void handleDelete(false);
                    }}
                    style={{ justifyContent: "flex-start", textAlign: "left" }}
                  >
                    Удалить из CRM
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setShowDeleteMenu(false);
                      void handleDelete(true);
                    }}
                    style={{
                      justifyContent: "flex-start",
                      textAlign: "left",
                      color: "var(--cold)",
                    }}
                  >
                    Удалить и больше не показывать
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ColdEmailDraft({ leadId, leadEmail }: { leadId: string; leadEmail?: string | null }) {
  const { t } = useLocale();
  const [draft, setDraft] = useState<LeadEmailDraft | null>(null);
  const [tone, setTone] = useState<EmailTone>("professional");
  const [extra, setExtra] = useState("");
  const [showExtra, setShowExtra] = useState(false);
  const [deepResearch, setDeepResearch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<"subject" | "body" | "all" | null>(null);
  const [sending, setSending] = useState(false);
  const [sentOk, setSentOk] = useState(false);
  const [sendErr, setSendErr] = useState<string | null>(null);
  const [gmailConnected, setGmailConnected] = useState<boolean | null>(null);
  const [outlookConnected, setOutlookConnected] = useState<boolean | null>(null);

  // Check which providers are connected once on mount.
  useEffect(() => {
    getGmailStatus()
      .then((s) => setGmailConnected(s.connected))
      .catch(() => setGmailConnected(false));
    getOutlookStatus()
      .then((s) => setOutlookConnected(s.connected))
      .catch(() => setOutlookConnected(false));
  }, []);

  const sendVia = async (provider: "gmail" | "outlook") => {
    if (!draft) return;
    setSending(true);
    setSendErr(null);
    setSentOk(false);
    try {
      await sendLeadEmail({
        leadId,
        subject: draft.subject,
        body: draft.body,
        to: leadEmail ?? undefined,
        provider,
      });
      setSentOk(true);
    } catch (e) {
      setSendErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  const generate = async (nextTone?: EmailTone) => {
    setBusy(true);
    setErr(null);
    try {
      const result = await draftLeadEmail(leadId, {
        tone: nextTone ?? tone,
        extraContext: extra.trim() || undefined,
        deepResearch,
      });
      setDraft(result);
      if (nextTone) setTone(nextTone);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const copy = async (kind: "subject" | "body" | "all") => {
    if (!draft) return;
    const text =
      kind === "subject"
        ? draft.subject
        : kind === "body"
          ? draft.body
          : `${draft.subject}\n\n${draft.body}`;
    try {
      await navigator.clipboard?.writeText(text);
      setCopied(kind);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      // ignore — clipboard may be unavailable
    }
  };

  if (!draft) {
    return (
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => generate()}
            disabled={busy}
          >
            <Icon name="mail" size={13} />
            {busy ? t("common.loading") : t("lead.email.generate")}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setShowExtra((v) => !v)}
          >
            {showExtra ? t("lead.email.hideExtra") : t("lead.email.addExtra")}
          </button>
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              cursor: "pointer",
              userSelect: "none",
              color: "var(--text-muted)",
            }}
            title={t("lead.email.deepResearchHint")}
          >
            <input
              type="checkbox"
              checked={deepResearch}
              onChange={(e) => setDeepResearch(e.target.checked)}
              style={{ accentColor: "var(--accent)" }}
            />
            <Icon
              name="sparkles"
              size={11}
              style={{ color: "var(--accent)" }}
            />
            {t("lead.email.deepResearch")}
          </label>
        </div>
        {showExtra && (
          <textarea
            className="textarea"
            rows={2}
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            placeholder={t("lead.email.extraPh")}
            maxLength={500}
            style={{ fontSize: 13 }}
          />
        )}
        {err && <div style={{ fontSize: 12, color: "var(--cold)" }}>{err}</div>}
      </div>
    );
  }

  return (
    <div
      style={{
        marginTop: 14,
        padding: 14,
        borderRadius: 12,
        border: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <div className="eyebrow" style={{ color: "var(--accent)" }}>
          <Icon name="mail" size={11} style={{ marginRight: 4, verticalAlign: "-2px" }} />
          {t("lead.email.draft")}
        </div>
        <div className="seg" style={{ fontSize: 11 }}>
          {TONES.map((tn) => (
            <button
              key={tn}
              type="button"
              className={tone === tn ? "active" : ""}
              onClick={() => generate(tn)}
              disabled={busy}
              style={{ fontSize: 11, padding: "4px 10px" }}
            >
              {t(`lead.email.tone.${tn}` as TranslationKey)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 4,
          }}
        >
          <div className="eyebrow" style={{ fontSize: 9, marginBottom: 0 }}>
            {t("lead.email.subject")}
          </div>
          <button
            type="button"
            onClick={() => copy("subject")}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 11,
              color: copied === "subject" ? "var(--hot)" : "var(--accent)",
              padding: 0,
            }}
          >
            {copied === "subject" ? t("lead.email.copied") : t("lead.email.copy")}
          </button>
        </div>
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            lineHeight: 1.4,
            padding: "8px 12px",
            background: "var(--surface-2)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          {draft.subject}
        </div>
      </div>

      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 4,
          }}
        >
          <div className="eyebrow" style={{ fontSize: 9, marginBottom: 0 }}>
            {t("lead.email.body")}
          </div>
          <button
            type="button"
            onClick={() => copy("body")}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 11,
              color: copied === "body" ? "var(--hot)" : "var(--accent)",
              padding: 0,
            }}
          >
            {copied === "body" ? t("lead.email.copied") : t("lead.email.copy")}
          </button>
        </div>
        <div
          style={{
            fontSize: 13.5,
            lineHeight: 1.55,
            padding: "10px 12px",
            background: "var(--surface-2)",
            borderRadius: 8,
            border: "1px solid var(--border)",
            whiteSpace: "pre-wrap",
          }}
        >
          {draft.body}
        </div>
      </div>

      {(draft.notable_facts.length > 0 || draft.recent_signal) && (
        <div
          style={{
            padding: "8px 10px",
            background:
              "color-mix(in srgb, var(--accent) 6%, var(--surface-2))",
            borderRadius: 8,
            border:
              "1px solid color-mix(in srgb, var(--accent) 18%, var(--border))",
            display: "flex",
            flexDirection: "column",
            gap: 4,
            fontSize: 12,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {draft.notable_facts.length > 0 && (
            <div>
              <div
                className="eyebrow"
                style={{
                  fontSize: 9,
                  marginBottom: 2,
                  color: "var(--accent)",
                }}
              >
                {t("lead.email.notableFacts")}
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {draft.notable_facts.map((f, i) => (
                  <li key={i} style={{ marginTop: 2 }}>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {draft.recent_signal && (
            <div style={{ marginTop: 4 }}>
              <span
                style={{
                  fontWeight: 600,
                  color: "var(--accent)",
                  marginRight: 4,
                }}
              >
                {t("lead.email.recentSignal")}
              </span>
              {draft.recent_signal}
            </div>
          )}
        </div>
      )}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => copy("all")}
          disabled={busy}
        >
          {copied === "all" ? t("lead.email.copied") : t("lead.email.copyAll")}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => generate()}
          disabled={busy}
        >
          <Icon name="sparkles" size={12} />
          {busy ? t("common.loading") : t("lead.email.regenerate")}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setShowExtra((v) => !v)}
        >
          {showExtra ? t("lead.email.hideExtra") : t("lead.email.addExtra")}
        </button>

        {/* Send buttons — shown once we know provider status */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {gmailConnected === true && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void sendVia("gmail")}
              disabled={sending || sentOk}
              style={sentOk ? { color: "var(--hot)" } : undefined}
            >
              <Icon name="send" size={12} />
              {sentOk
                ? t("lead.email.sent")
                : sending
                  ? t("common.loading")
                  : t("lead.email.sendGmail")}
            </button>
          )}
          {outlookConnected === true && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => void sendVia("outlook")}
              disabled={sending || sentOk}
            >
              <Icon name="send" size={12} />
              {sentOk ? t("lead.email.sent") : sending ? t("common.loading") : t("lead.email.sendOutlook")}
            </button>
          )}
          {gmailConnected === false && outlookConnected === false && (
            <a
              href="/app/settings"
              className="btn btn-ghost btn-sm"
              style={{ opacity: 0.7, fontSize: 12 }}
            >
              <Icon name="mail" size={12} />
              {t("lead.email.connectEmail")}
            </a>
          )}
        </div>
      </div>
      {showExtra && (
        <textarea
          className="textarea"
          rows={2}
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          placeholder={t("lead.email.extraPh")}
          maxLength={500}
          style={{ fontSize: 13 }}
        />
      )}
      {sendErr && (
        <div style={{ fontSize: 12, color: "var(--cold)", marginTop: 4 }}>
          {sendErr}
        </div>
      )}
      {err && <div style={{ fontSize: 12, color: "var(--cold)" }}>{err}</div>}
    </div>
  );
}
