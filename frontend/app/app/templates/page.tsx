"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  type OutreachTemplate,
  createOutreachTemplate,
  deleteOutreachTemplate,
  listOutreachTemplates,
  updateOutreachTemplate,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { EmptyState } from "@/components/app/EmptyState";
import { SEED_TEMPLATES } from "@/lib/seedTemplates";

const TONE_OPTIONS = ["professional", "casual", "bold"] as const;
type Tone = (typeof TONE_OPTIONS)[number];

interface DraftState {
  id: string | null;
  name: string;
  subject: string;
  body: string;
  tone: Tone;
}

const EMPTY_DRAFT: DraftState = {
  id: null,
  name: "",
  subject: "",
  body: "",
  tone: "professional",
};

export default function TemplatesPage() {
  const { t } = useLocale();
  const [items, setItems] = useState<OutreachTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    listOutreachTemplates({ teamId: activeTeamId() })
      .then((r) => {
        if (!cancelled) setItems(r.items);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const startNew = () => setDraft({ ...EMPTY_DRAFT });
  const startEdit = (it: OutreachTemplate) =>
    setDraft({
      id: it.id,
      name: it.name,
      subject: it.subject ?? "",
      body: it.body,
      tone: TONE_OPTIONS.includes(it.tone as Tone)
        ? (it.tone as Tone)
        : "professional",
    });

  const cancelDraft = () => setDraft(null);

  const save = async () => {
    if (!draft) return;
    if (draft.name.trim().length < 1 || draft.body.trim().length < 1) return;
    setBusy(true);
    setError(null);
    try {
      if (draft.id) {
        await updateOutreachTemplate(draft.id, {
          name: draft.name.trim(),
          subject: draft.subject.trim() || null,
          body: draft.body.trim(),
          tone: draft.tone,
        });
      } else {
        await createOutreachTemplate({
          name: draft.name.trim(),
          subject: draft.subject.trim() || null,
          body: draft.body.trim(),
          tone: draft.tone,
          teamId: activeTeamId(),
        });
      }
      setDraft(null);
      setTick((n) => n + 1);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setError(detail);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await deleteOutreachTemplate(id);
      setTick((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Topbar
        title={t("templates.title")}
        subtitle={t("templates.subtitle")}
        right={
          !draft ? (
            <button type="button" className="btn btn-sm" onClick={startNew}>
              <Icon name="plus" size={13} /> {t("templates.new")}
            </button>
          ) : null
        }
      />
      <div className="page" style={{ maxWidth: 980 }}>
        {error && (
          <div
            className="card"
            style={{
              padding: 14,
              color: "var(--cold)",
              borderColor: "var(--cold)",
              marginBottom: 16,
            }}
          >
            {error}
          </div>
        )}

        {draft && (
          <div className="card" style={{ padding: 22, marginBottom: 18 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 14,
              }}
            >
              <div className="eyebrow">
                {draft.id
                  ? t("templates.editor.titleEdit")
                  : t("templates.editor.titleNew")}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={cancelDraft}
                  disabled={busy}
                >
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={save}
                  disabled={
                    busy ||
                    draft.name.trim().length < 1 ||
                    draft.body.trim().length < 1
                  }
                >
                  {busy
                    ? t("common.loading")
                    : t("templates.editor.save")}
                </button>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <Field label={t("templates.field.name")}>
                <input
                  className="input"
                  value={draft.name}
                  maxLength={120}
                  onChange={(e) =>
                    setDraft({ ...draft, name: e.target.value })
                  }
                  placeholder={t("templates.field.namePh")}
                  autoFocus
                />
              </Field>
              <Field label={t("templates.field.subject")}>
                <input
                  className="input"
                  value={draft.subject}
                  maxLength={255}
                  onChange={(e) =>
                    setDraft({ ...draft, subject: e.target.value })
                  }
                  placeholder={t("templates.field.subjectPh")}
                />
              </Field>
              <Field
                label={t("templates.field.body")}
                hint={t("templates.field.bodyHint")}
              >
                <textarea
                  className="textarea"
                  rows={9}
                  value={draft.body}
                  maxLength={4000}
                  onChange={(e) =>
                    setDraft({ ...draft, body: e.target.value })
                  }
                  placeholder={t("templates.field.bodyPh")}
                />
                <div
                  style={{
                    marginTop: 4,
                    fontSize: 11.5,
                    color: "var(--text-dim)",
                    textAlign: "right",
                  }}
                >
                  {draft.body.length} / 4000
                </div>
              </Field>
              <Field label={t("templates.field.tone")}>
                <div style={{ display: "flex", gap: 6 }}>
                  {TONE_OPTIONS.map((tone) => {
                    const active = draft.tone === tone;
                    return (
                      <button
                        key={tone}
                        type="button"
                        onClick={() => setDraft({ ...draft, tone })}
                        style={{
                          padding: "7px 13px",
                          fontSize: 13,
                          borderRadius: 999,
                          cursor: "pointer",
                          border: active
                            ? "1px solid var(--accent)"
                            : "1px solid var(--border)",
                          background: active
                            ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                            : "var(--surface)",
                          color: active ? "var(--accent)" : "var(--text)",
                          fontWeight: active ? 600 : 500,
                        }}
                      >
                        {t(`lead.email.tone.${tone}`)}
                      </button>
                    );
                  })}
                </div>
              </Field>
            </div>
          </div>
        )}

        {items === null ? null : items.length === 0 ? (
          <EmptyState
            icon="mail"
            title={t("templates.empty.title")}
            body={t("templates.empty.body")}
            actions={
              !draft
                ? [
                    {
                      label: t("templates.new"),
                      onClick: startNew,
                      variant: "primary",
                    },
                  ]
                : undefined
            }
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                gap: 10,
                width: "100%",
                maxWidth: 620,
                marginTop: 6,
              }}
            >
              {SEED_TEMPLATES.map((tpl) => (
                <button
                  key={tpl.name}
                  type="button"
                  disabled={busy}
                  className="card card-hover"
                  style={{
                    cursor: "pointer",
                    textAlign: "left",
                    padding: "12px 14px",
                    background: "var(--surface-2)",
                  }}
                  onClick={async () => {
                    setBusy(true);
                    setError(null);
                    try {
                      await createOutreachTemplate({
                        name: tpl.name,
                        subject: tpl.subject,
                        body: tpl.body,
                        tone: tpl.tone,
                        teamId: activeTeamId() ?? undefined,
                      });
                      setTick((n) => n + 1);
                    } catch (e) {
                      setError(
                        e instanceof Error ? e.message : String(e),
                      );
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      marginBottom: 4,
                    }}
                  >
                    {tpl.name}
                  </div>
                  <div
                    style={{
                      fontSize: 11.5,
                      color: "var(--text-muted)",
                      lineHeight: 1.4,
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {tpl.body}
                  </div>
                </button>
              ))}
            </div>
          </EmptyState>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {items.map((it) => (
              <div
                key={it.id}
                className="card"
                style={{ padding: 18 }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    justifyContent: "space-between",
                    gap: 12,
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 14.5,
                        fontWeight: 700,
                        marginBottom: 4,
                      }}
                    >
                      {it.name}
                    </div>
                    {it.subject && (
                      <div
                        style={{
                          fontSize: 12.5,
                          color: "var(--text-muted)",
                          marginBottom: 8,
                        }}
                      >
                        {t("templates.field.subject")}: {it.subject}
                      </div>
                    )}
                    <div
                      style={{
                        fontSize: 13,
                        color: "var(--text-muted)",
                        lineHeight: 1.55,
                        whiteSpace: "pre-wrap",
                        maxHeight: 130,
                        overflow: "hidden",
                        position: "relative",
                      }}
                    >
                      {it.body}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span
                      className="chip"
                      style={{
                        fontSize: 10.5,
                        padding: "3px 8px",
                      }}
                    >
                      {t(`lead.email.tone.${it.tone}` as TranslationKey)}
                    </span>
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    marginTop: 12,
                    paddingTop: 12,
                    borderTop: "1px solid var(--border)",
                  }}
                >
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => startEdit(it)}
                  >
                    <Icon name="pencil" size={12} /> {t("common.edit")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      if (typeof navigator !== "undefined") {
                        navigator.clipboard
                          .writeText(it.body)
                          .catch(() => undefined);
                      }
                    }}
                  >
                    <Icon name="check" size={12} /> {t("templates.copy")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => remove(it.id)}
                    disabled={busy}
                    style={{ marginLeft: "auto", color: "var(--cold)" }}
                  >
                    <Icon name="x" size={12} /> {t("common.delete")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        <span>{label}</span>
        {hint && (
          <span
            style={{
              fontSize: 10.5,
              fontWeight: 500,
              color: "var(--text-dim)",
              textTransform: "none",
              letterSpacing: 0,
            }}
          >
            {hint}
          </span>
        )}
      </label>
      {children}
    </div>
  );
}
