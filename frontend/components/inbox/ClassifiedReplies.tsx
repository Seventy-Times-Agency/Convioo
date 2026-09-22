"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui";
import { getClassifiedReplies, type ClassifiedReply } from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/**
 * Входящие — Inbox.dc.html.
 *
 * Экран строится на разборе ИИ, а не на почтовых тредах: ради разбора
 * сюда и заходят. Категория, выжимка и черновик ответа пишутся
 * классификатором в активность лида, поэтому список работает и тогда,
 * когда ящик синхронизирован не полностью.
 */

const CATEGORY_KEYS: Record<string, TranslationKey> = {
  interested: "inbox.cat.interested",
  meeting_request: "inbox.cat.meeting",
  question: "inbox.cat.question",
  objection: "inbox.cat.objection",
  not_interested: "inbox.cat.notInterested",
  unsubscribe: "inbox.cat.unsubscribe",
  auto_reply: "inbox.cat.autoReply",
  referral: "inbox.cat.referral",
  other: "inbox.cat.other",
};

const TONE: Record<string, string> = {
  interested: "var(--hot)",
  meeting_request: "var(--hot)",
  objection: "var(--warm)",
  question: "var(--warm)",
  unsubscribe: "var(--cold)",
  not_interested: "var(--cold)",
};

export function ClassifiedReplies() {
  const { t } = useLocale();
  const [items, setItems] = useState<ClassifiedReply[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [cat, setCat] = useState<string>("all");
  const [activeId, setActiveId] = useState<string | null>(null);
  // Пространство выставляет сайдбар, и часто позже, чем монтируется
  // этот блок. Без подписки список грузился бы для «личного» режима,
  // где командных ответов нет, и экран оставался бы пустым.
  const [tick, setTick] = useState(0);
  useEffect(() => subscribeWorkspace(() => setTick((n) => n + 1)), []);

  useEffect(() => {
    getClassifiedReplies(activeTeamId())
      .then((d) => {
        setItems(d.replies);
        setCounts(d.counts);
        setActiveId((prev) => prev ?? d.replies[0]?.id ?? null);
      })
      .catch(() => undefined);
  }, [tick]);

  const shown = useMemo(
    () => (cat === "all" ? items : items.filter((r) => r.category === cat)),
    [items, cat],
  );
  const active = items.find((r) => r.id === activeId) ?? shown[0] ?? null;

  if (items.length === 0) return null;

  const label = (c: string) =>
    CATEGORY_KEYS[c] ? t(CATEGORY_KEYS[c]) : c;

  return (
    <div style={{ marginBottom: 18 }}>
      <div
        style={{
          display: "flex",
          gap: 6,
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        {["all", ...Object.keys(counts).filter((k) => k !== "all")].map((c) => (
          <button
            key={c}
            type="button"
            className={cat === c ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
            onClick={() => setCat(c)}
          >
            {c === "all" ? t("inbox.cat.all") : label(c)} · {counts[c] ?? 0}
          </button>
        ))}
        <span
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginLeft: "auto",
          }}
        >
          {t("inbox.aiHint")}
        </span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 340px) minmax(0, 1fr)",
          gap: 12,
          alignItems: "start",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {shown.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setActiveId(r.id)}
              style={{
                textAlign: "left",
                border: "1px solid var(--border)",
                borderColor:
                  active?.id === r.id ? "var(--accent)" : "var(--border)",
                background:
                  active?.id === r.id
                    ? "color-mix(in srgb, var(--accent) 6%, transparent)"
                    : "var(--surface)",
                borderRadius: 10,
                padding: "10px 12px",
                cursor: "pointer",
                display: "grid",
                gap: 3,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <span style={{ fontSize: 13.5, fontWeight: 700 }}>
                  {r.lead_name}
                </span>
                <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                  {new Date(r.at).toLocaleString("ru-RU", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {r.preview}
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span
                  className="chip"
                  style={{
                    fontSize: 10,
                    color: TONE[r.category] ?? "var(--text-muted)",
                    borderColor: TONE[r.category] ?? "var(--border)",
                  }}
                >
                  {label(r.category)}
                </span>
                {r.suggested_reply && (
                  <span style={{ fontSize: 10.5, color: "var(--accent)" }}>
                    {t("inbox.draftReady")}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>

        {active && (
          <div className="card" style={{ padding: 16 }}>
            <div style={{ fontSize: 16, fontWeight: 800 }}>
              {active.lead_name}
            </div>
            {active.summary && (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-dim)",
                  marginTop: 3,
                }}
              >
                {t("inbox.aiVerdict")}: {active.summary}
              </div>
            )}

            <div
              style={{
                marginTop: 14,
                padding: "12px 14px",
                borderRadius: 10,
                background: "var(--surface-2)",
                fontSize: 13.5,
                lineHeight: 1.55,
              }}
            >
              «{active.preview}»
            </div>

            {active.suggested_reply ? (
              <>
                <div className="eyebrow" style={{ margin: "16px 0 6px" }}>
                  {t("inbox.draftTitle")}
                </div>
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 10,
                    background: "var(--accent-soft)",
                    border:
                      "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
                    fontSize: 13.5,
                    lineHeight: 1.55,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {active.suggested_reply}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                  <Button
                    size="sm"
                    onClick={() =>
                      navigator.clipboard?.writeText(
                        active.suggested_reply ?? "",
                      )
                    }
                  >
                    <Icon name="copy" size={14} />
                    {t("inbox.copyDraft")}
                  </Button>
                </div>
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--text-dim)",
                    marginTop: 8,
                    lineHeight: 1.5,
                  }}
                >
                  {t("inbox.sendHint")}
                </div>
              </>
            ) : (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-dim)",
                  marginTop: 14,
                }}
              >
                {t("inbox.noDraft")}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
