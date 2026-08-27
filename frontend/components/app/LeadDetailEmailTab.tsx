"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  type EmailDraftLanguage,
  type EmailTone,
  type LeadEmailDraft,
  draftLeadEmail,
  getGmailStatus,
  sendLeadEmail,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { showError } from "@/lib/toast";

const TONES: EmailTone[] = ["professional", "casual", "bold"];

// "auto" follows the interface language (the request omits `language`).
type EmailLangChoice = "auto" | EmailDraftLanguage;

const EMAIL_LANG_NAMES: Record<EmailDraftLanguage, string> = {
  ru: "Русский",
  uk: "Українська",
  en: "English",
};

function EmailLanguageSelect({
  value,
  onChange,
  disabled,
}: {
  value: EmailLangChoice;
  onChange: (v: EmailLangChoice) => void;
  disabled?: boolean;
}) {
  const { t } = useLocale();
  return (
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
        value={value}
        onChange={(e) => onChange(e.target.value as EmailLangChoice)}
        disabled={disabled}
        style={{ fontSize: 11, padding: "3px 6px", width: "auto" }}
      >
        <option value="auto">{t("lead.email.language.auto")}</option>
        {(Object.keys(EMAIL_LANG_NAMES) as EmailDraftLanguage[]).map((l) => (
          <option key={l} value={l}>
            {EMAIL_LANG_NAMES[l]}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ColdEmailDraft({ leadId }: { leadId: string }) {
  const { t } = useLocale();
  const [draft, setDraft] = useState<LeadEmailDraft | null>(null);
  const [tone, setTone] = useState<EmailTone>("professional");
  const [emailLang, setEmailLang] = useState<EmailLangChoice>("auto");
  const [extra, setExtra] = useState("");
  const [showExtra, setShowExtra] = useState(false);
  const [deepResearch, setDeepResearch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<"subject" | "body" | "all" | null>(null);

  // Gmail send-as-user state. We resolve the connection status lazily —
  // the first time the user opens the send pane — so opening the lead
  // modal doesn't spam /api/v1/oauth/gmail for everyone.
  const [showSendForm, setShowSendForm] = useState(false);
  const [gmailReady, setGmailReady] = useState<
    "unknown" | "checking" | "ready" | "missing"
  >("unknown");
  const [gmailFromEmail, setGmailFromEmail] = useState<string | null>(null);
  const [sendTo, setSendTo] = useState("");
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState<string | null>(null);
  const [sendOk, setSendOk] = useState(false);

  useEffect(() => {
    if (!showSendForm || gmailReady !== "unknown") return;
    setGmailReady("checking");
    void getGmailStatus()
      .then((s) => {
        if (s.connected) {
          setGmailReady("ready");
          setGmailFromEmail(s.account_email);
        } else {
          setGmailReady("missing");
        }
      })
      .catch(() => setGmailReady("missing"));
  }, [showSendForm, gmailReady]);

  const submitSend = async () => {
    if (!draft) return;
    setSending(true);
    setSendErr(null);
    setSendOk(false);
    try {
      await sendLeadEmail({
        leadId,
        subject: draft.subject,
        body: draft.body,
        to: sendTo.trim() || undefined,
      });
      setSendOk(true);
      // Auto-collapse after a short success blink so the user can reopen
      // it for another lead without the form lingering.
      setTimeout(() => {
        setShowSendForm(false);
        setSendOk(false);
        setSendTo("");
      }, 2200);
    } catch (e) {
      setSendErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  const generate = async (nextTone?: EmailTone) => {
    setBusy(true);
    try {
      const result = await draftLeadEmail(leadId, {
        tone: nextTone ?? tone,
        extraContext: extra.trim() || undefined,
        deepResearch,
        language: emailLang === "auto" ? undefined : emailLang,
      });
      setDraft(result);
      if (nextTone) setTone(nextTone);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
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
          <EmailLanguageSelect
            value={emailLang}
            onChange={setEmailLang}
            disabled={busy}
          />
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
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <EmailLanguageSelect
            value={emailLang}
            onChange={setEmailLang}
            disabled={busy}
          />
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
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setShowSendForm((v) => !v)}
          disabled={sending}
          style={{ marginLeft: "auto" }}
        >
          <Icon name="send" size={12} />
          {t("lead.email.sendGmail")}
        </button>
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
      {showSendForm && (
        <div
          style={{
            marginTop: 6,
            padding: 12,
            border: "1px solid var(--border)",
            borderRadius: 10,
            background: "var(--surface-2)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
            fontSize: 12.5,
          }}
        >
          {gmailReady === "checking" && (
            <div style={{ color: "var(--text-muted)" }}>
              {t("common.loading")}
            </div>
          )}
          {gmailReady === "missing" && (
            <div style={{ color: "var(--text-muted)", lineHeight: 1.5 }}>
              {t("lead.sendEmail.notConnected")}{" "}
              <a
                href="/app/settings/integrations"
                style={{ color: "var(--accent)" }}
              >
                {t("lead.sendEmail.connectGmail")}
              </a>
              .
            </div>
          )}
          {gmailReady === "ready" && (
            <>
              <div style={{ color: "var(--text-muted)" }}>
                {t("lead.sendEmail.from")}{" "}
                <strong style={{ color: "var(--text)" }}>
                  {gmailFromEmail ?? "—"}
                </strong>
              </div>
              <input
                className="input"
                type="email"
                value={sendTo}
                onChange={(e) => setSendTo(e.target.value)}
                placeholder={t("lead.sendEmail.toPh")}
                disabled={sending || sendOk}
                style={{ fontSize: 13 }}
              />
              <div style={{ color: "var(--text-muted)", fontSize: 11.5 }}>
                {t("lead.sendEmail.toHint")}
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => void submitSend()}
                  disabled={sending || sendOk}
                >
                  {sending
                    ? t("lead.sendEmail.sending")
                    : sendOk
                      ? t("lead.sendEmail.sent")
                      : t("lead.sendEmail.confirm")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setShowSendForm(false);
                    setSendErr(null);
                    setSendTo("");
                  }}
                  disabled={sending}
                >
                  {t("common.cancel")}
                </button>
              </div>
              {sendErr && (
                <div style={{ color: "var(--cold)", fontSize: 12 }}>
                  {sendErr}
                </div>
              )}
              {sendOk && (
                <div style={{ color: "var(--hot)", fontSize: 12 }}>
                  {t("lead.sendEmail.successLogged")}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
