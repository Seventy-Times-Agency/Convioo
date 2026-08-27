"use client";

import { useEffect, useState } from "react";
import {
  createWebhook,
  deleteWebhook,
  listWebhooks,
  testWebhook,
  updateWebhook,
  type Webhook,
  type WebhookCreated,
} from "@/lib/api";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { useLocale } from "@/lib/i18n";

const ALLOWED_EVENTS = [
  { id: "lead.created", label: "lead.created", hintKey: "settings.webhooks.event.leadCreated" },
  { id: "lead.status_changed", label: "lead.status_changed", hintKey: "settings.webhooks.event.leadStatusChanged" },
  { id: "search.finished", label: "search.finished", hintKey: "settings.webhooks.event.searchFinished" },
] as const;

export function WebhooksSection() {
  const { t } = useLocale();
  const [items, setItems] = useState<Webhook[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  const [draftUrl, setDraftUrl] = useState("");
  const [draftEvents, setDraftEvents] = useState<string[]>([
    "lead.created",
    "lead.status_changed",
  ]);
  const [draftDescription, setDraftDescription] = useState("");
  const [justCreated, setJustCreated] = useState<WebhookCreated | null>(null);

  const refresh = async () => {
    try {
      const r = await listWebhooks();
      setItems(r.items);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const toggleDraftEvent = (id: string) => {
    setDraftEvents((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setInfo(null);
    if (draftEvents.length === 0) {
      showError(t("settings.webhooks.error.noEvent"));
      return;
    }
    if (!draftUrl.trim()) {
      showError(t("settings.webhooks.error.noUrl"));
      return;
    }
    setBusy(true);
    try {
      const created = await createWebhook({
        targetUrl: draftUrl.trim(),
        eventTypes: draftEvents,
        description: draftDescription.trim() || undefined,
      });
      setJustCreated(created);
      setDraftUrl("");
      setDraftDescription("");
      await refresh();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (row: Webhook) => {
    setBusy(true);
    try {
      await updateWebhook(row.id, { active: !row.active });
      await refresh();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: Webhook) => {
    if (!(await confirmAsync(t("settings.webhooks.confirmDelete", { url: row.target_url })))) return;
    setBusy(true);
    try {
      await deleteWebhook(row.id);
      await refresh();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async (row: Webhook) => {
    setBusy(true);
    setInfo(null);
    try {
      await testWebhook(row.id);
      setInfo(t("settings.webhooks.testQueued"));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Webhooks
      </div>
      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 14,
        }}
      >
        {t("settings.webhooks.descIntro")}{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>
          X-Convioo-Signature: sha256=…
        </code>
        . {t("settings.webhooks.descPayload")}{" "}
        <a
          href="/developers#webhooks"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "var(--accent)" }}
        >
          /developers
        </a>
        .
      </div>

      {justCreated && (
        <div
          style={{
            border: "1px solid var(--accent)",
            background: "var(--accent-soft)",
            borderRadius: 10,
            padding: 12,
            marginBottom: 14,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            {t("settings.webhooks.createdCopySecret")}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <code
              style={{
                flex: 1,
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                padding: "6px 8px",
                background: "var(--surface)",
                borderRadius: 6,
                wordBreak: "break-all",
              }}
            >
              {justCreated.secret}
            </code>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                void navigator.clipboard?.writeText(justCreated.secret);
              }}
            >
              {t("settings.copy")}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setJustCreated(null)}
            >
              {t("settings.ok")}
            </button>
          </div>
        </div>
      )}

      <form
        onSubmit={submitCreate}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
          marginBottom: 14,
        }}
      >
        <input
          className="input"
          value={draftUrl}
          onChange={(e) => setDraftUrl(e.target.value)}
          placeholder="https://your-service.example.com/convioo-hook"
          style={{ fontSize: 13 }}
        />
        <input
          className="input"
          value={draftDescription}
          onChange={(e) => setDraftDescription(e.target.value)}
          placeholder={t("settings.webhooks.descriptionPlaceholder")}
          style={{ fontSize: 13 }}
        />
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            fontSize: 12.5,
          }}
        >
          {ALLOWED_EVENTS.map((ev) => {
            const checked = draftEvents.includes(ev.id);
            return (
              <label
                key={ev.id}
                style={{
                  display: "inline-flex",
                  gap: 6,
                  alignItems: "center",
                  padding: "6px 10px",
                  borderRadius: 8,
                  border: checked
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: checked ? "var(--accent-soft)" : "transparent",
                  cursor: "pointer",
                }}
                title={t(ev.hintKey)}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleDraftEvent(ev.id)}
                />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                  {ev.label}
                </span>
              </label>
            );
          })}
        </div>
        <div>
          <button type="submit" className="btn btn-sm" disabled={busy}>
            {busy ? "..." : t("settings.webhooks.create")}
          </button>
        </div>
      </form>

      {info && (
        <div style={{ fontSize: 13, color: "var(--accent)", marginBottom: 10 }}>
          {info}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {items === null ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {t("common.loading")}
          </div>
        ) : items.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {t("settings.webhooks.empty")}
          </div>
        ) : (
          items.map((w) => (
            <div
              key={w.id}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 10,
                padding: 12,
                opacity: w.active ? 1 : 0.5,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  marginBottom: 8,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 12.5,
                      fontWeight: 600,
                      wordBreak: "break-all",
                    }}
                  >
                    {w.target_url}
                  </div>
                  {w.description && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        marginTop: 2,
                      }}
                    >
                      {w.description}
                    </div>
                  )}
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                      marginTop: 6,
                      fontSize: 11,
                    }}
                  >
                    {w.event_types.map((e) => (
                      <span
                        key={e}
                        style={{
                          fontFamily: "var(--font-mono)",
                          padding: "2px 6px",
                          border: "1px solid var(--border)",
                          borderRadius: 4,
                          color: "var(--text-muted)",
                        }}
                      >
                        {e}
                      </span>
                    ))}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void sendTest(w)}
                    disabled={busy || !w.active}
                  >
                    {t("settings.webhooks.test")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void toggleActive(w)}
                    disabled={busy}
                  >
                    {w.active ? t("settings.webhooks.disable") : t("settings.webhooks.enable")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void remove(w)}
                    disabled={busy}
                    style={{ color: "var(--cold)" }}
                  >
                    {t("common.delete")}
                  </button>
                </div>
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  display: "flex",
                  gap: 14,
                  flexWrap: "wrap",
                }}
              >
                <span>
                  {t("settings.webhooks.secret")} {" "}
                  <code style={{ fontFamily: "var(--font-mono)" }}>
                    {w.secret_preview}
                  </code>
                </span>
                <span>
                  {w.last_delivery_at
                    ? t("settings.webhooks.lastDelivery", {
                        time: new Date(w.last_delivery_at).toLocaleString(),
                        status: w.last_delivery_status ?? "?",
                      })
                    : t("settings.webhooks.neverDelivered")}
                </span>
                {w.failure_count > 0 && (
                  <span style={{ color: "var(--cold)" }}>
                    {t("settings.webhooks.failuresInRow", { count: w.failure_count })}
                  </span>
                )}
                {w.last_failure_message && (
                  <span style={{ color: "var(--cold)" }}>
                    {w.last_failure_message.slice(0, 80)}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
