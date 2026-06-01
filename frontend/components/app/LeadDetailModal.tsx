"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { LeadDetailExtras } from "@/components/app/LeadDetailExtras";
import {
  type Lead,
  type LeadMarkColor,
  type LeadStatus,
  LEAD_MARK_COLORS,
  LEAD_MARK_HEX,
  archiveLead,
  deleteLead,
  leadMarkHex,
  reEnrichLead,
  setLeadMark,
  unarchiveLead,
  tempOf,
  updateLead,
} from "@/lib/api";
import { TagEditor } from "@/components/app/TagEditor";
import { ColdEmailDraft } from "@/components/app/LeadDetailEmailTab";
import { useLocale } from "@/lib/i18n";
import { statusColorHex, useTeamLeadStatuses } from "@/lib/leadStatuses";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

export function LeadDetailModal({
  lead,
  onClose,
  onUpdated,
  onDeleted,
  onArchived,
  emailTrigger,
  noteTrigger,
}: {
  lead: Lead;
  onClose: () => void;
  onUpdated?: (updated: Lead) => void;
  onDeleted?: (leadId: string, forever: boolean) => void;
  onArchived?: (leadId: string, archived: boolean) => void;
  emailTrigger?: number;
  noteTrigger?: number;
}) {
  const { t } = useLocale();
  const { statuses } = useTeamLeadStatuses();
  const [status, setStatus] = useState<LeadStatus>(lead.lead_status);
  const [note, setNote] = useState(lead.notes ?? "");
  const [dealValue, setDealValue] = useState<string>(
    lead.deal_value != null ? String(lead.deal_value) : "",
  );
  const [saving, setSaving] = useState(false);
  const [reenriching, setReenriching] = useState(false);
  const [markColor, setMarkColor] = useState<string | null>(lead.mark_color);
  const [markBusy, setMarkBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteMenu, setShowDeleteMenu] = useState(false);
  const [showScoreBreakdown, setShowScoreBreakdown] = useState(false);

  useEffect(() => {
    if (!emailTrigger) return;
    const el = document.getElementById("lead-email-section");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [emailTrigger]);

  useEffect(() => {
    if (!noteTrigger) return;
    const el = document.getElementById("lead-note-field");
    if (el) (el as HTMLTextAreaElement).focus();
  }, [noteTrigger]);

  useEffect(() => {
    if (!emailTrigger) return;
    const el = document.getElementById("lead-email-section");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [emailTrigger]);

  useEffect(() => {
    if (!noteTrigger) return;
    const el = document.getElementById("lead-note-field");
    if (el) (el as HTMLTextAreaElement).focus();
  }, [noteTrigger]);

  const pickColor = async (color: LeadMarkColor | null) => {
    setMarkBusy(true);
    const previous = markColor;
    setMarkColor(color);
    try {
      const updated = await setLeadMark(lead.id, color);
      onUpdated?.(updated);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
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
    try {
      const parsed = dealValue.trim() !== "" ? parseFloat(dealValue) : null;
      const updated = await updateLead(lead.id, {
        lead_status: status,
        notes: note,
        deal_value: parsed,
      });
      onUpdated?.(updated);
      onClose();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleReenrich = async () => {
    setReenriching(true);
    try {
      const updated = await reEnrichLead(lead.id);
      onUpdated?.(updated);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setReenriching(false);
    }
  };

  const handleDelete = async (forever: boolean) => {
    const confirmText = forever
      ? t("lead.delete.foreverConfirm")
      : t("lead.delete.fromCrmConfirm");
    if (!(await confirmAsync(confirmText))) return;
    setDeleting(true);
    try {
      await deleteLead(lead.id, { forever });
      onDeleted?.(lead.id, forever);
      onClose();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  };

  const isArchived = lead.archived_at != null;
  const handleArchiveToggle = async () => {
    const confirmText = isArchived
      ? t("lead.archive.restoreConfirm")
      : t("lead.archive.toArchiveConfirm");
    if (!(await confirmAsync(confirmText))) return;
    try {
      if (isArchived) {
        await unarchiveLead(lead.id);
      } else {
        await archiveLead(lead.id);
      }
      onArchived?.(lead.id, !isArchived);
      onClose();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
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
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        {/* Шапка — фиксирована, не скроллится с телом */}
        <div
          style={{
            padding: "20px 24px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            background: "var(--surface)",
            flexShrink: 0,
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
              <div className="eyebrow" style={{ fontSize: 10 }}>{t("lead.aiScore")}</div>
              {lead.score_components && (
                <button
                  type="button"
                  onClick={() => setShowScoreBreakdown((v) => !v)}
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    cursor: "pointer",
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginTop: 2,
                  }}
                >
                  {showScoreBreakdown
                    ? t("common.hide")
                    : t("lead.scoreBreakdown")}
                </button>
              )}
            </div>
            <button className="btn-icon" onClick={onClose} type="button">
              <Icon name="x" size={18} />
            </button>
          </div>
        </div>

        {/* Скроллящаяся середина — занимает всё свободное пространство */}
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>

        {showScoreBreakdown && lead.score_components && (
          <div
            style={{
              padding: "12px 28px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {(
              [
                { key: "rating", labelKey: "lead.score.rating", max: 35 },
                { key: "website", labelKey: "lead.score.website", max: 25 },
                { key: "social", labelKey: "lead.score.social", max: 20 },
                { key: "email", labelKey: "lead.score.email", max: 10 },
                { key: "recency", labelKey: "lead.score.recency", max: 10 },
              ] as const
            ).map(({ key, labelKey, max }) => {
              const val = lead.score_components?.[key] ?? 0;
              return (
                <div key={key} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", width: 72, flexShrink: 0 }}>
                    {t(labelKey)}
                  </span>
                  <div
                    style={{
                      flex: 1,
                      height: 6,
                      borderRadius: 3,
                      background: "var(--border)",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: `${Math.round((val / max) * 100)}%`,
                        height: "100%",
                        background: "var(--accent)",
                        borderRadius: 3,
                      }}
                    />
                  </div>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", width: 44, textAlign: "right", flexShrink: 0 }}>
                    +{val}/{max}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        <div
          style={{
            padding: "20px 24px",
            display: "grid",
            gridTemplateColumns: "1.4fr 1fr",
            gap: 20,
            alignItems: "start",
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
                <div id="lead-email-section">
                  <ColdEmailDraft leadId={lead.id} />
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
              <div className="eyebrow" style={{ marginBottom: 8 }}>{t("lead.tags")}</div>
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
                id="lead-note-field"
                className="textarea"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={t("lead.notesPh")}
                rows={3}
              />
            </div>

            <LeadDetailExtras leadId={lead.id} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {/* Воронка — статус + ценность сделки + метка в одной карточке */}
            <div className="card" style={{ padding: 14 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                {t("lead.status")}
              </div>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 6,
                  marginBottom: 14,
                }}
              >
                {statuses.map((s) => {
                  const active = status === s.key;
                  const dot = statusColorHex(s.key, statuses);
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setStatus(s.key)}
                      style={{
                        padding: "5px 10px",
                        borderRadius: 999,
                        cursor: "pointer",
                        fontSize: 12,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        background: active
                          ? "color-mix(in srgb, " + dot + " 18%, transparent)"
                          : "var(--surface-2)",
                        color: active ? "var(--text)" : "var(--text-muted)",
                        border:
                          "1px solid " +
                          (active
                            ? "color-mix(in srgb, " + dot + " 50%, transparent)"
                            : "transparent"),
                        fontWeight: active ? 600 : 500,
                      }}
                    >
                      <span
                        style={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          background: dot,
                        }}
                      />
                      {s.label}
                    </button>
                  );
                })}
              </div>

              <div
                className="eyebrow"
                style={{ marginBottom: 8, fontSize: 10 }}
              >
                {t("lead.dealValue")}
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 14,
                }}
              >
                <span
                  style={{
                    color: "var(--text-muted)",
                    fontSize: 14,
                    fontWeight: 600,
                  }}
                >
                  $
                </span>
                <input
                  type="number"
                  className="input"
                  min={0}
                  placeholder="0"
                  value={dealValue}
                  onChange={(e) => setDealValue(e.target.value)}
                  style={{ flex: 1, fontSize: 13 }}
                />
                {dealValue.trim() !== "" &&
                  !isNaN(parseFloat(dealValue)) && (
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {parseFloat(dealValue).toLocaleString("en-US", {
                        style: "currency",
                        currency: "USD",
                        maximumFractionDigits: 0,
                      })}
                    </span>
                  )}
              </div>

              <div
                className="eyebrow"
                style={{
                  fontSize: 10,
                  marginBottom: 8,
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
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
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
                        width: 22,
                        height: 22,
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
            </div>

            {/* Контакты — без вложенной карточки, чистый список */}
            <div className="card" style={{ padding: 14 }}>
              <div className="eyebrow" style={{ marginBottom: 10 }}>
                {t("lead.contact")}
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                {lead.phone && (
                  <div
                    style={{ display: "flex", alignItems: "center", gap: 10 }}
                  >
                    <Icon
                      name="phone"
                      size={14}
                      style={{ color: "var(--text-dim)", flexShrink: 0 }}
                    />
                    <span>{lead.phone}</span>
                  </div>
                )}
                {lead.website && (
                  <div
                    style={{ display: "flex", alignItems: "center", gap: 10 }}
                  >
                    <Icon
                      name="globe"
                      size={14}
                      style={{ color: "var(--text-dim)", flexShrink: 0 }}
                    />
                    <a
                      href={
                        lead.website.startsWith("http")
                          ? lead.website
                          : `https://${lead.website}`
                      }
                      target="_blank"
                      rel="noreferrer noopener"
                      style={{
                        color: "var(--accent)",
                        wordBreak: "break-all",
                      }}
                    >
                      {lead.website}
                    </a>
                  </div>
                )}
                {lead.address && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      color: "var(--text-muted)",
                    }}
                  >
                    <Icon
                      name="mapPin"
                      size={14}
                      style={{ marginTop: 3, flexShrink: 0 }}
                    />
                    <span>{lead.address}</span>
                  </div>
                )}
                {lead.rating !== null && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                    }}
                  >
                    <Icon
                      name="star"
                      size={14}
                      style={{ color: "var(--warm)", flexShrink: 0 }}
                    />
                    <span>
                      <b>{lead.rating}</b> · {lead.reviews_count ?? 0}{" "}
                      {t("lead.rating")}
                    </span>
                  </div>
                )}
                {Object.keys(socialLinks).length > 0 && (
                  <div
                    style={{
                      borderTop: "1px solid var(--border)",
                      paddingTop: 8,
                      marginTop: 2,
                      display: "flex",
                      gap: 6,
                      flexWrap: "wrap",
                    }}
                  >
                    {Object.entries(socialLinks).map(([k, v]) => (
                      <span
                        key={k}
                        className="chip"
                        style={{ fontSize: 11 }}
                      >
                        {k}: {v}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div
                style={{
                  marginTop: 14,
                  paddingTop: 12,
                  borderTop: "1px solid var(--border)",
                }}
              >
                <div className="eyebrow" style={{ fontSize: 10, marginBottom: 6 }}>
                  {t("lead.decisionMaker")}
                </div>
                {lead.website_meta?.contact_person ? (
                  <>
                    <div style={{ fontSize: 13.5 }}>
                      <b>{lead.website_meta.contact_person.name}</b>
                      {lead.website_meta.contact_person.title && (
                        <span style={{ color: "var(--text-muted)" }}>
                          {" — " + lead.website_meta.contact_person.title}
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                        marginTop: 2,
                      }}
                    >
                      {lead.website_meta.contact_person.source_label}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                    {t("lead.decisionMaker.empty")}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        </div>
        {/* /scroll wrapper */}

        {/* Sticky футер с действиями — единая панель внизу модалки */}
        <div
          style={{
            padding: "14px 24px",
            borderTop: "1px solid var(--border)",
            background: "var(--surface)",
            display: "flex",
            gap: 8,
            alignItems: "center",
            flexWrap: "wrap",
            position: "relative",
          }}
        >
          <button
            className="btn btn-sm"
            disabled={saving || deleting || reenriching}
            onClick={save}
            type="button"
          >
            <Icon name="check" size={13} />
            {saving ? t("common.saving") : t("common.save")}
          </button>
          <button
            className="btn btn-ghost btn-sm"
            disabled={saving || deleting || reenriching}
            onClick={() => void handleReenrich()}
            type="button"
            title={t("lead.reenrich.title")}
          >
            <Icon name="sparkles" size={13} />
            {reenriching ? "..." : t("lead.reenrich")}
          </button>
          <a
            href={`${process.env.NEXT_PUBLIC_API_URL}/api/v1/leads/${lead.id}/audit-pdf`}
            target="_blank"
            rel="noopener noreferrer"
            download
            className="btn btn-ghost btn-sm"
            style={{ textDecoration: "none" }}
          >
            <Icon name="download" size={13} />
            {t("lead.auditPdf")}
          </a>
          <div style={{ flex: 1 }} />
          <button
            className="btn btn-ghost btn-sm"
            style={{ color: "var(--cold)" }}
            disabled={saving || deleting}
            onClick={() => setShowDeleteMenu((v) => !v)}
            type="button"
            aria-haspopup="true"
            aria-expanded={showDeleteMenu}
            title={t("common.delete")}
          >
            <Icon name="trash" size={13} />
          </button>
          {showDeleteMenu && (
            <div
              style={{
                position: "absolute",
                bottom: "calc(100% + 6px)",
                right: 16,
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
                  void handleArchiveToggle();
                }}
                style={{ justifyContent: "flex-start", textAlign: "left" }}
              >
                {isArchived ? t("lead.unarchive") : t("lead.archive")}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowDeleteMenu(false);
                  void handleDelete(false);
                }}
                style={{ justifyContent: "flex-start", textAlign: "left" }}
              >
                {t("lead.delete.fromCrm")}
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
                {t("lead.delete.forever")}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

