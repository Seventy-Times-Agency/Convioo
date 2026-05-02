"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  bulkDraftEmails,
  type BulkDraftEmailItem,
  type Lead,
} from "@/lib/api";
import { Icon } from "@/components/Icon";

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
  const [items, setItems] = useState<BulkDraftEmailItem[] | null>(null);
  const [tone, setTone] = useState<string>("professional");
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const generate = async () => {
    setBusy(true);
    setError(null);
    setItems(null);
    try {
      const result = await bulkDraftEmails({
        leadIds: leads.map((l) => l.id),
        tone,
        extraContext: extra.trim() || null,
      });
      setItems(result.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
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
              Письма для {leads.length} лид{plural(leads.length)}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              AI пишет персонализированные cold-email черновики. Можно
              скопировать каждый отдельно или все разом.
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
            Тон
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
                {opt}
              </button>
            );
          })}
          <input
            className="input"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            placeholder="Доп. контекст (например, упомянуть наш кейс с N)"
            style={{ flex: 1, minWidth: 200, fontSize: 12 }}
          />
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => void generate()}
            disabled={busy}
          >
            {busy ? "Пишу…" : "Сгенерировать заново"}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void copyAll()}
            disabled={!items || busy}
            style={{ color: "var(--accent)" }}
          >
            {copied === "ALL" ? "Скопировано" : "Скопировать все"}
          </button>
        </div>

        {error && (
          <div
            style={{
              padding: "10px 24px",
              fontSize: 13,
              color: "var(--cold)",
            }}
          >
            {error}
          </div>
        )}

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
                      {copied === item.lead_id ? "Скопировано" : "Скопировать"}
                    </button>
                  </div>
                  {item.error ? (
                    <div style={{ fontSize: 12, color: "var(--cold)" }}>
                      Ошибка: {item.error}
                    </div>
                  ) : !item.subject ? (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      Генерируется…
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

function plural(n: number): string {
  // Russian plural agreement: 1 → "а", 2-4 → "ов", 5+ → "ов".
  if (n % 100 >= 11 && n % 100 <= 14) return "ов";
  const last = n % 10;
  if (last === 1) return "а";
  if (last >= 2 && last <= 4) return "ов";
  return "ов";
}
