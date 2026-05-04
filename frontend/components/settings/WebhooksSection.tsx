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

const ALLOWED_EVENTS = [
  { id: "lead.created", label: "lead.created", hint: "Новый лид доставлен в CRM" },
  { id: "lead.status_changed", label: "lead.status_changed", hint: "Изменился статус лида" },
  { id: "search.finished", label: "search.finished", hint: "Поиск завершён (успешно или с ошибкой)" },
] as const;

export function WebhooksSection() {
  const [items, setItems] = useState<Webhook[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      setError(e instanceof Error ? e.message : String(e));
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
    setError(null);
    setInfo(null);
    if (draftEvents.length === 0) {
      setError("Выберите хотя бы одно событие.");
      return;
    }
    if (!draftUrl.trim()) {
      setError("Укажите target URL.");
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
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (row: Webhook) => {
    setBusy(true);
    setError(null);
    try {
      await updateWebhook(row.id, { active: !row.active });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: Webhook) => {
    if (!confirm(`Удалить webhook ${row.target_url}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteWebhook(row.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async (row: Webhook) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await testWebhook(row.id);
      setInfo(
        "Тестовый webhook поставлен в очередь. Проверь свой endpoint через несколько секунд.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
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
        Convioo отправит подписанный POST на твой URL, когда событие
        случится. Подпись — заголовок{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>
          X-Convioo-Signature: sha256=…
        </code>
        . Формат payload и проверка HMAC описаны на странице{" "}
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
            Webhook создан. Скопируй секрет — повторно показать не сможем:
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
              Скопировать
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setJustCreated(null)}
            >
              ОК
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
          placeholder="Описание (необязательно)"
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
                title={ev.hint}
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
            {busy ? "..." : "Создать webhook"}
          </button>
        </div>
      </form>

      {error && (
        <div style={{ fontSize: 13, color: "var(--cold)", marginBottom: 10 }}>
          {error}
        </div>
      )}
      {info && (
        <div style={{ fontSize: 13, color: "var(--accent)", marginBottom: 10 }}>
          {info}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {items === null ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Загрузка…
          </div>
        ) : items.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Подписок пока нет.
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
                    Тест
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void toggleActive(w)}
                    disabled={busy}
                  >
                    {w.active ? "Выключить" : "Включить"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void remove(w)}
                    disabled={busy}
                    style={{ color: "var(--cold)" }}
                  >
                    Удалить
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
                  Секрет: {" "}
                  <code style={{ fontFamily: "var(--font-mono)" }}>
                    {w.secret_preview}
                  </code>
                </span>
                <span>
                  {w.last_delivery_at
                    ? `Последняя доставка: ${new Date(w.last_delivery_at).toLocaleString()} (${w.last_delivery_status ?? "?"})`
                    : "Ещё не доставлялся"}
                </span>
                {w.failure_count > 0 && (
                  <span style={{ color: "var(--cold)" }}>
                    Ошибок подряд: {w.failure_count}
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
