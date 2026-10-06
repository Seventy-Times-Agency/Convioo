"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/brand/Icon";
import {
  ActivityBlock,
  CustomFieldsBlock,
  TasksBlock,
} from "@/components/leads/LeadDetailExtras";
import {
  type EmailStatus,
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
  verifyLeadEmail,
} from "@/lib/api";
import { TagEditor } from "@/components/leads/TagEditor";
import { EmailStatusBadge } from "@/components/leads/EmailStatusBadge";
import { ColdEmailDraft } from "@/components/leads/LeadDetailEmailTab";
import { LeadCalls } from "@/components/leads/LeadCalls";
import { useLocale } from "@/lib/i18n";
import { statusColorHex, useTeamLeadStatuses } from "@/lib/leadStatuses";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";

type Tab = "overview" | "history" | "tasks" | "email";

const SCORE_PARTS = [
  { key: "rating", labelKey: "lead.score.rating", max: 35 },
  { key: "website", labelKey: "lead.score.website", max: 25 },
  { key: "social", labelKey: "lead.score.social", max: 20 },
  { key: "email", labelKey: "lead.score.email", max: 10 },
  { key: "recency", labelKey: "lead.score.recency", max: 10 },
] as const;

/**
 * Карточка лида. Шапка — кто это и что с ним делать (позвонить,
 * написать, сохранить); под ней полоса контактов в одну строку и
 * статус; дальше вкладки: обзор (разбор ИИ, ЛПР, сделка, заметки,
 * скор), история (звонки + активность), задачи и поля, письмо.
 */
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
  const [showMenu, setShowMenu] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [callsCount, setCallsCount] = useState<number | null>(null);
  const [contactEmail, setContactEmail] = useState<string | null>(
    lead.contact_email ?? lead.website_meta?.emails?.[0] ?? null,
  );
  const [emailStatus, setEmailStatus] = useState<EmailStatus | null>(
    lead.email_status ?? null,
  );
  const [verifying, setVerifying] = useState(false);

  const reverifyEmail = async () => {
    setVerifying(true);
    const prevStatus = emailStatus;
    // Optimistic: show the unverified/checking pill while the request runs.
    setEmailStatus("unknown");
    try {
      const res = await verifyLeadEmail(lead.id);
      setContactEmail(res.contact_email);
      setEmailStatus((res.email_status as EmailStatus | null) ?? null);
    } catch (e) {
      setEmailStatus(prevStatus);
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setVerifying(false);
    }
  };

  // Внешние триггеры (из списка): «написать» открывает вкладку письма,
  // «заметка» — обзор с фокусом в поле.
  useEffect(() => {
    if (!emailTrigger) return;
    setTab("email");
  }, [emailTrigger]);

  useEffect(() => {
    if (!noteTrigger) return;
    setTab("overview");
    window.setTimeout(() => {
      const el = document.getElementById("lead-note-field");
      if (el) (el as HTMLTextAreaElement).focus();
    }, 0);
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

  const scoreColor =
    score >= 75 ? "var(--hot)" : score >= 50 ? "#B45309" : "var(--cold)";
  const dm = lead.website_meta?.contact_person ?? null;
  const dmOthers = (dm?.people ?? []).filter((p) => p.name !== dm?.name);
  const busy = saving || deleting || reenriching;

  const tabs: { key: Tab; label: string; count?: number | null }[] = [
    { key: "overview", label: t("lead.tab.overview") },
    { key: "history", label: t("lead.tab.history"), count: callsCount },
    { key: "tasks", label: t("lead.tab.tasks") },
    { key: "email", label: t("lead.tab.email") },
  ];

  const sectionTitle = (text: string, color?: string) => (
    <div className="eyebrow" style={{ marginBottom: 8, color }}>
      {text}
    </div>
  );

  const box = (children: React.ReactNode, extra?: React.CSSProperties) => (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "12px 14px",
        background: "var(--surface)",
        ...extra,
      }}
    >
      {children}
    </div>
  );

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
          maxWidth: 920,
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--shadow-lg)",
          overflow: "hidden",
        }}
      >
        {/* Шапка: скор · имя · действия */}
        <div
          style={{
            padding: "14px 20px",
            display: "flex",
            alignItems: "center",
            gap: 14,
            flexShrink: 0,
          }}
        >
          <div
            title={t("lead.aiScore")}
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              flexShrink: 0,
              display: "grid",
              placeItems: "center",
              fontFamily: "var(--font-mono)",
              fontSize: 18,
              fontWeight: 700,
              color: scoreColor,
              background: `color-mix(in srgb, ${scoreColor} 12%, transparent)`,
            }}
          >
            {score}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {markColor && (
                <span
                  title={t("lead.mark.title")}
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: leadMarkHex(markColor) ?? "var(--text-dim)",
                    flexShrink: 0,
                  }}
                />
              )}
              <span
                style={{
                  fontSize: 20,
                  fontWeight: 700,
                  letterSpacing: "-0.02em",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {lead.name}
              </span>
              <span className={"chip chip-" + temp} style={{ fontSize: 11 }}>
                <span className={"status-dot " + temp} />
                {temp}
              </span>
              {isArchived && (
                <span className="chip" style={{ fontSize: 11 }}>
                  {t("lead.archive")}
                </span>
              )}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                marginTop: 2,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {[lead.category, lead.address].filter(Boolean).join(" · ")}
            </div>
          </div>

          <select
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            style={{ width: "auto", fontSize: 12, padding: "3px 8px", maxWidth: 170 }}
            title={t("lead.status")}
          >
            {statuses.map((s) => (
              <option key={s.id} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          {lead.phone && (
            <a href={`/app/work?lead=${lead.id}`} className="btn btn-primary btn-sm">
              <Icon name="phone" size={13} />
              {t("lead.callInWork")}
            </a>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setTab("email")}
          >
            <Icon name="mail" size={13} />
            {t("lead.tab.email")}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={busy}
            onClick={save}
          >
            <Icon name="check" size={13} />
            {saving ? t("common.saving") : t("common.save")}
          </button>
          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="btn-icon"
              onClick={() => setShowMenu((v) => !v)}
              aria-haspopup="true"
              aria-expanded={showMenu}
              title={t("lead.more")}
            >
              <Icon name="moreH" size={16} />
            </button>
            {showMenu && (
              <div
                style={{
                  position: "absolute",
                  top: "calc(100% + 6px)",
                  right: 0,
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  padding: 6,
                  boxShadow: "0 8px 24px rgba(15,15,20,0.12)",
                  minWidth: 240,
                  zIndex: 5,
                  display: "flex",
                  flexDirection: "column",
                  gap: 2,
                }}
                onMouseLeave={() => setShowMenu(false)}
              >
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={busy}
                  style={{ justifyContent: "flex-start" }}
                  title={t("lead.reenrich.title")}
                  onClick={() => {
                    setShowMenu(false);
                    void handleReenrich();
                  }}
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
                  style={{ justifyContent: "flex-start", textDecoration: "none" }}
                >
                  <Icon name="download" size={13} />
                  {t("lead.auditPdf")}
                </a>
                <div style={{ borderTop: "1px solid var(--border)", margin: "4px 0" }} />
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: "flex-start" }}
                  onClick={() => {
                    setShowMenu(false);
                    void handleArchiveToggle();
                  }}
                >
                  <Icon name="archive" size={13} />
                  {isArchived ? t("lead.unarchive") : t("lead.archive")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: "flex-start" }}
                  onClick={() => {
                    setShowMenu(false);
                    void handleDelete(false);
                  }}
                >
                  <Icon name="trash" size={13} />
                  {t("lead.delete.fromCrm")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ justifyContent: "flex-start", color: "var(--cold)" }}
                  onClick={() => {
                    setShowMenu(false);
                    void handleDelete(true);
                  }}
                >
                  <Icon name="trash" size={13} />
                  {t("lead.delete.forever")}
                </button>
              </div>
            )}
          </div>
          <button className="btn-icon" onClick={onClose} type="button">
            <Icon name="x" size={18} />
          </button>
        </div>

        {/* Полоса контактов + статус */}
        <div
          style={{
            padding: "8px 20px",
            background: "var(--surface-2)",
            borderTop: "1px solid var(--border)",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 14,
            flexWrap: "wrap",
            fontSize: 12.5,
            flexShrink: 0,
          }}
        >
          {lead.phone && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="phone" size={13} style={{ color: "var(--text-dim)" }} />
              {lead.phone}
            </span>
          )}
          {lead.website && (
            <a
              href={lead.website.startsWith("http") ? lead.website : `https://${lead.website}`}
              target="_blank"
              rel="noreferrer noopener"
              style={{
                color: "var(--accent)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                maxWidth: 220,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              <Icon name="globe" size={13} style={{ color: "var(--text-dim)", flexShrink: 0 }} />
              {lead.website.replace(/^https?:\/\//, "")}
            </a>
          )}
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <Icon name="mail" size={13} style={{ color: "var(--text-dim)" }} />
            {contactEmail ? (
              <a href={`mailto:${contactEmail}`} style={{ color: "var(--accent)" }}>
                {contactEmail}
              </a>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>{t("lead.email.noAddress")}</span>
            )}
            {(contactEmail || emailStatus) && <EmailStatusBadge status={emailStatus} size="sm" />}
            <button
              type="button"
              className="btn-icon"
              onClick={() => void reverifyEmail()}
              disabled={verifying}
              title={verifying ? t("lead.email.verifying") : t("lead.email.reverify")}
              style={{ width: 22, height: 22, opacity: verifying ? 0.5 : 1 }}
            >
              <Icon name="rotateCcw" size={12} />
            </button>
          </span>
          {lead.rating !== null && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Icon name="star" size={13} style={{ color: "var(--warm)" }} />
              <b>{lead.rating}</b>
              <span style={{ color: "var(--text-muted)" }}>
                ({lead.reviews_count ?? 0})
              </span>
            </span>
          )}
          {Object.entries(socialLinks).map(([k, v]) => (
            <a
              key={k}
              href={v.startsWith("http") ? v : `https://${v}`}
              target="_blank"
              rel="noreferrer noopener"
              className="chip"
              style={{ fontSize: 11 }}
              title={v}
            >
              {k}
            </a>
          ))}
        </div>

        {/* Вкладки */}
        <div
          style={{
            display: "flex",
            padding: "0 20px",
            borderBottom: "1px solid var(--border)",
            flexShrink: 0,
          }}
        >
          {tabs.map((tb) => {
            const active = tab === tb.key;
            return (
              <button
                key={tb.key}
                type="button"
                onClick={() => setTab(tb.key)}
                style={{
                  background: "none",
                  border: "none",
                  borderBottom: "2px solid " + (active ? "var(--accent)" : "transparent"),
                  padding: "9px 12px",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: active ? 600 : 500,
                  color: active ? "var(--text)" : "var(--text-muted)",
                }}
              >
                {tb.label}
                {tb.count != null && tb.count > 0 && (
                  <span style={{ color: "var(--text-dim)", marginLeft: 6, fontWeight: 400 }}>
                    {tb.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Тело вкладки */}
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "14px 20px 18px" }}>
          {/* Звонки грузятся в фоне, чтобы счётчик на вкладке был сразу;
              рисуются только в «Истории». */}
          <div style={{ display: tab === "history" ? "block" : "none" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                {sectionTitle(t("calls.title"))}
                <LeadCalls leadId={lead.id} onCount={setCallsCount} showTitle={false} />
                {callsCount === 0 && (
                  <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                    {t("lead.history.noCalls")}
                  </div>
                )}
              </div>
              <ActivityBlock leadId={lead.id} />
            </div>
          </div>

          {tab === "overview" && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.4fr 1fr",
                gap: 12,
                alignItems: "start",
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {lead.advice &&
                  box(
                    <>
                      {sectionTitle(t("lead.howToPitch"), "var(--accent)")}
                      <div style={{ fontSize: 13.5, lineHeight: 1.6 }}>{lead.advice}</div>
                    </>,
                    {
                      background: "var(--accent-soft)",
                      borderColor: "color-mix(in srgb, var(--accent) 20%, transparent)",
                    },
                  )}

                {(strengths.length > 0 || weaknesses.length > 0 || redFlags.length > 0) &&
                  box(
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                        gap: 12,
                      }}
                    >
                      {(
                        [
                          [t("lead.strengths"), strengths, "var(--hot)"],
                          [t("lead.weaknesses"), weaknesses, "#B45309"],
                          [t("lead.redFlags"), redFlags, "var(--cold)"],
                        ] as const
                      ).map(([title, items, color]) => (
                        <div key={title} style={{ minWidth: 0 }}>
                          {sectionTitle(title, color)}
                          {items.length === 0 ? (
                            <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>—</div>
                          ) : (
                            <ul
                              style={{
                                margin: 0,
                                paddingLeft: 16,
                                fontSize: 12.5,
                                lineHeight: 1.5,
                                color: "var(--text)",
                              }}
                            >
                              {items.map((s, i) => (
                                <li key={i} style={{ marginBottom: 3 }}>
                                  {s}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}
                    </div>,
                  )}

                {box(
                  <>
                    {sectionTitle(t("lead.notes"))}
                    <textarea
                      id="lead-note-field"
                      className="textarea"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder={t("lead.notesPh")}
                      rows={3}
                    />
                  </>,
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {box(
                  <>
                    {sectionTitle(t("lead.decisionMaker"))}
                    {dm ? (
                      <>
                        <div style={{ fontSize: 13.5 }}>
                          <b>{dm.name}</b>
                          {dm.title && (
                            <span style={{ color: "var(--text-muted)" }}> — {dm.title}</span>
                          )}
                        </div>
                        {(dm.email || dm.phone) && (
                          <div
                            style={{
                              display: "flex",
                              gap: 12,
                              flexWrap: "wrap",
                              fontSize: 12.5,
                              marginTop: 4,
                            }}
                          >
                            {dm.email && <a href={`mailto:${dm.email}`}>{dm.email}</a>}
                            {dm.phone && <a href={`tel:${dm.phone}`}>{dm.phone}</a>}
                          </div>
                        )}
                        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
                          {dm.source_label}
                        </div>
                        {dmOthers.length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <div className="eyebrow" style={{ fontSize: 9.5, marginBottom: 4 }}>
                              {t("lead.dm.others")}
                            </div>
                            {dmOthers.map((p) => (
                              <div key={p.name} style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                {p.name}
                                {p.title ? ` — ${p.title}` : ""}
                                {p.email ? ` · ${p.email}` : ""}
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    ) : (
                      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                        {t("lead.decisionMaker.empty")}
                      </div>
                    )}
                  </>,
                )}

                {box(
                  <>
                    {sectionTitle(t("lead.deal"))}
                    <div style={{ display: "grid", gap: 10, fontSize: 13 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ color: "var(--text-muted)", width: 64, flexShrink: 0 }}>
                          {t("lead.dealValue")}
                        </span>
                        <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>$</span>
                        <input
                          type="number"
                          className="input"
                          min={0}
                          placeholder="0"
                          value={dealValue}
                          onChange={(e) => setDealValue(e.target.value)}
                          style={{ flex: 1, fontSize: 13, padding: "4px 8px" }}
                        />
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ color: "var(--text-muted)", width: 64, flexShrink: 0 }}>
                          {t("lead.mark.title")}
                        </span>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
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
                                  width: 18,
                                  height: 18,
                                  borderRadius: "50%",
                                  background: LEAD_MARK_HEX[c],
                                  border: active ? "2px solid var(--text)" : "2px solid transparent",
                                  boxShadow: active ? "0 0 0 1px var(--surface) inset" : "none",
                                  cursor: markBusy ? "wait" : "pointer",
                                  padding: 0,
                                }}
                              />
                            );
                          })}
                        </div>
                      </div>
                      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                        <span style={{ color: "var(--text-muted)", width: 64, flexShrink: 0, paddingTop: 4 }}>
                          {t("lead.tags")}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <TagEditor
                            leadId={lead.id}
                            initialTags={lead.user_tags ?? []}
                            onChanged={(tags) => {
                              onUpdated?.({ ...lead, user_tags: tags });
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </>,
                )}

                {lead.score_components &&
                  box(
                    <>
                      {sectionTitle(t("lead.scoreBreakdownTitle", { n: score }))}
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {SCORE_PARTS.map(({ key, labelKey, max }) => {
                          const val = lead.score_components?.[key] ?? 0;
                          return (
                            <div key={key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 12, color: "var(--text-muted)", width: 64, flexShrink: 0 }}>
                                {t(labelKey)}
                              </span>
                              <div
                                style={{
                                  flex: 1,
                                  height: 5,
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
                                  }}
                                />
                              </div>
                              <span
                                style={{
                                  fontSize: 11.5,
                                  color: "var(--text-muted)",
                                  width: 40,
                                  textAlign: "right",
                                  fontVariantNumeric: "tabular-nums",
                                }}
                              >
                                {val}/{max}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </>,
                  )}
              </div>
            </div>
          )}

          {tab === "tasks" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
              <TasksBlock leadId={lead.id} />
              <CustomFieldsBlock leadId={lead.id} />
            </div>
          )}

          {tab === "email" && (
            <div id="lead-email-section">
              <ColdEmailDraft leadId={lead.id} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
