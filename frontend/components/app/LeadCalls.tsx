"use client";

import { useEffect, useRef, useState } from "react";
import {
  callRecordingUrl,
  getLeadCalls,
  type CallRecord,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const OUTCOME_KEYS: Record<string, TranslationKey> = {
  goal: "calls.outcome.goal",
  callback: "calls.outcome.callback",
  thinking: "calls.outcome.thinking",
  no_answer: "calls.outcome.no_answer",
  refused: "calls.outcome.refused",
  wrong_number: "calls.outcome.wrong_number",
};

/**
 * Звонки лида через телефонию: запись, разбор ИИ и расшифровка.
 * Пусто — блок не рисуется: без телефонии или до первого звонка
 * карточке нечего показывать.
 */
export function LeadCalls({ leadId }: { leadId: string }) {
  const { t } = useLocale();
  const [calls, setCalls] = useState<CallRecord[] | null>(null);
  const [openTranscript, setOpenTranscript] = useState<string | null>(null);

  const callsRef = useRef<CallRecord[] | null>(null);
  callsRef.current = calls;

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getLeadCalls(leadId)
        .then((rows) => {
          if (!cancelled) setCalls(rows);
        })
        .catch(() => {
          if (!cancelled) setCalls([]);
        });
    void load();
    // Пока звонок в обработке (запись → текст → разбор), подтягиваем
    // раз в 15 секунд; когда всё разобрано — перестаём.
    const pending = new Set(["dialing", "completed", "transcribed"]);
    const timer = window.setInterval(() => {
      if (callsRef.current?.some((c) => pending.has(c.state))) void load();
    }, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [leadId]);

  if (!calls || calls.length === 0) return null;

  const mmss = (sec: number | null) => {
    if (!sec) return "0:00";
    return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  };

  const stateLabel = (c: CallRecord) => {
    switch (c.state) {
      case "dialing":
        return t("calls.state.dialing");
      case "missed":
        return t("calls.state.missed");
      case "completed":
      case "transcribed":
        return t("calls.state.processing");
      case "failed":
        return t("calls.state.failed");
      default:
        return null;
    }
  };

  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>
        {t("calls.title")}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {calls.map((c) => {
          const a = c.analysis;
          const status = stateLabel(c);
          return (
            <div
              key={c.id}
              className="card"
              style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                  fontSize: 12,
                  color: "var(--text-dim)",
                }}
              >
                <span>
                  {new Date(c.created_at).toLocaleString("ru-RU", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  {c.user_name ? ` · ${c.user_name}` : ""}
                </span>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {t("calls.talk", { time: mmss(c.talk_sec) })}
                </span>
              </div>

              {status && (
                <div style={{ fontSize: 12, color: c.state === "failed" ? "var(--cold)" : "var(--text-muted)" }}>
                  {status}
                </div>
              )}

              {c.has_recording && (
                <audio
                  controls
                  preload="none"
                  src={callRecordingUrl(c.id)}
                  style={{ width: "100%", height: 34 }}
                />
              )}

              {a && (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 13, lineHeight: 1.5 }}>
                  {a.summary && <div>{a.summary}</div>}
                  {a.next_step && (
                    <div>
                      <b>{t("calls.nextStep")}:</b> {a.next_step}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {a.suggested_outcome && OUTCOME_KEYS[a.suggested_outcome] && (
                      <span className="chip" style={{ fontSize: 11, color: "var(--accent)", borderColor: "var(--accent)" }}>
                        {t("calls.suggested")}: {t(OUTCOME_KEYS[a.suggested_outcome])}
                      </span>
                    )}
                    {typeof a.quality_score === "number" && (
                      <span className="chip" style={{ fontSize: 11 }}>
                        {t("calls.quality", { n: a.quality_score })}
                      </span>
                    )}
                    {(a.objections ?? []).map((o) => (
                      <span key={o} className="chip" style={{ fontSize: 11, color: "var(--warm)", borderColor: "var(--warm)" }}>
                        {o}
                      </span>
                    ))}
                  </div>
                  {a.quality_notes && (
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {a.quality_notes}
                    </div>
                  )}
                </div>
              )}

              {c.transcript && c.transcript.length > 0 && (
                <>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ alignSelf: "flex-start" }}
                    onClick={() =>
                      setOpenTranscript((prev) => (prev === c.id ? null : c.id))
                    }
                  >
                    {openTranscript === c.id
                      ? t("calls.hideTranscript")
                      : t("calls.showTranscript")}
                  </button>
                  {openTranscript === c.id && (
                    <div
                      style={{
                        maxHeight: 260,
                        overflowY: "auto",
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                        fontSize: 12.5,
                        lineHeight: 1.5,
                        background: "var(--surface-2)",
                        borderRadius: 8,
                        padding: 10,
                      }}
                    >
                      {c.transcript.map((s, i) => (
                        <div key={i}>
                          <b
                            style={{
                              color:
                                s.speaker === "client"
                                  ? "var(--accent)"
                                  : "var(--text-muted)",
                            }}
                          >
                            {s.speaker === "rep"
                              ? t("calls.speakerRep")
                              : s.speaker === "client"
                                ? t("calls.speakerClient")
                                : s.speaker}
                            :
                          </b>{" "}
                          {s.text}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
