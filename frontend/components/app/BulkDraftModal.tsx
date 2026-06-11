"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  bulkDraftEmails,
  type BulkDraftEmailItem,
  type EmailDraftLanguage,
  type Lead,
} from "@/lib/api";
import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

/**
 * Generates cold-email drafts for the selected leads in one shot.
 *
 * The drafts come back asynchronously — we render placeholders, then
 * swap in subject + body as the batch endpoint resolves. Per-lead
 * errors get inlined; one bad lead doesn't kill the batch.
 */
export function BulkDraftModal({
  leads,
  onClose,
}: {
  leads: Lead[];
  onClose: () => void;
}) {
  const { t } = useLocale();
  const [items, setItems] = useState<BulkDraftEmailItem[] | null>(null);
  const [tone, setTone] = useState<string>("professional");
  const [emailLang, setEmailLang] = useState<"auto" | EmailDraftLanguage>(
    "auto",
  );
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const generate = async () => {
    setBusy(true);
    setItems(null);
    try {
      const result = await bulkDraftEmails({
        leadIds: leads.map((l) => l.id),
        tone,
        extraContext: extra.trim() || null,
        language: emailLang === "auto" ? undefined : emailLang,
      });
      setItems(result.items);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const copyOne = async (item: BulkDraftEmailItem) => {
    if (!item.subject || !item.body) return;
    try {
      await navigator.clipboard.writeText(
        `${item.subject}\n\n${item.body}`,
      );
      setCopied(item.lead_id);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      // ignore — clipboard may be unavailable
    }
  };

  const copyAll = async () => {
    if (!items) return;
    const blocks: string[] = [];
    for (const item of items) {
      const lead = leads.find((l) => l.id === item.lead_id);
      blocks.push(
        `### ${lead?.name ?? "(unknown)"}\n` +
          (item.subject ? `Subject: ${item.subject}\n\n` : "") +
          (item.body ?? item.error ?? ""),
      );
    }
    try {
      await navigator.clipboard.writeText(blocks.join("\n\n---\n\n"));
      setCopied("ALL");
      setTimeout(() => setCopied(null), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,15,20,0.4)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          borderRadius: 16,
          width: "min(820px, 100%)",
          maxHeight: "92vh",
          overflowY: "auto",
          boxShadow: "0 16px 56px rgba(15,15,20,0.18)",
        }}
      >
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div>
            <div style={{ fontSize: 17, fontWeight: 700 }}>
              {t("crm.bulkDraft.title", { count: leads.length })}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              {t("crm.bulkDraft.subtitle")}
            </div>
          </div>
          <button className="btn-icon" onClick={onClose} type="button">
            <Icon name="x" size={18} />
          </button>
        </div>

        <div
          style={{
            padding: "14px 24px",
            display: "flex",
            gap: 10,
            alignItems: "center",
            flexWrap: "wrap",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span className="eyebrow" style={{ fontSize: 10 }}>
            {t("crm.bulkDraft.tone")}
          </span>
          {(["professional", "casual", "bold"] as const).map((opt) => {
            const active = tone === opt;
            return (
              <button
                key={opt}
                type="button"
                onClick={() => setTone(opt)}
                disabled={busy}
                style={{
                  padding: "4px 11px",
                  fontSize: 12,
                  borderRadius: 999,
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                  cursor: busy ? "wait" : "pointer",
                }}
              >
                {opt === "professional"
                  ? t("lead.email.tone.professional")
                  : opt === "casual"
                    ? t("lead.email.tone.casual")
                    : t("lead.email.tone.bold")}
              </button>
            );
          })}
          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
            {t("lead.email.language")}
            <select
              className="input"
              value={emailLang}
              onChange={(e) =>
                setEmailLang(e.target.value as "auto" | EmailDraftLanguage)
              }
              disabled={busy}
              style={{ fontSize: 11, padding: "3px 6px", width: "auto" }}
            >
              <option value="auto">{t("lead.email.language.auto")}</option>
              <option value="ru">Русский</option>
              <option value="uk">Українська</option>
              <option value="en">English</option>
            </select>
          </label>
          <input
            className="input"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            placeholder={t("crm.bulkDraft.extraPh")}
            style={{ flex: 1, minWidth: 200, fontSize: 12 }}
          />
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => void generate()}
            disabled={busy}
          >
            {busy ? t("crm.bulkDraft.writing") : t("crm.bulkDraft.regenerate")}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void copyAll()}
            disabled={!items || busy}
            style={{ color: "var(--accent)" }}
          >
            {copied === "ALL" ? t("common.copied") : t("common.copyAll")}
          </button>
        </div>

        <div style={{ padding: "10px 24px 24px", display: "flex", flexDirection: "column", gap: 14 }}>
          {(items ?? leads.map((l) => ({ lead_id: l.id, subject: null, body: null, error: null }))).map(
            (item) => {
              const lead = leads.find((l) => l.id === item.lead_id);
              return (
                <div
                  key={item.lead_id}
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    padding: 14,
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 12,
                    }}
                  >
                    <div style={{ fontSize: 14, fontWeight: 600 }}>
                      {lead?.name ?? item.lead_id}
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={!item.subject || !item.body}
                      onClick={() => void copyOne(item)}
                    >
                      {copied === item.lead_id
                        ? t("common.copied")
                        : t("common.copy")}
                    </button>
                  </div>
                  {item.error ? (
                    <div style={{ fontSize: 12, color: "var(--cold)" }}>
                      {t("crm.bulkDraft.error", { error: item.error })}
                    </div>
                  ) : !item.subject ? (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {t("crm.bulkDraft.generating")}
                    </div>
                  ) : (
                    <>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>
                        {item.subject}
                      </div>
                      <pre
                        style={{
                          margin: 0,
                          fontSize: 13,
                          lineHeight: 1.55,
                          whiteSpace: "pre-wrap",
                          fontFamily: "inherit",
                          color: "var(--text)",
                        }}
                      >
                        {item.body}
                      </pre>
                    </>
                  )}
                </div>
              );
            },
          )}
        </div>
      </div>
    </div>
  );
}
