"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/brand/Icon";
import { RecordingPlayer } from "@/components/work/RecordingPlayer";
import { RubricView } from "@/components/work/RubricView";
import { TranscriptView } from "@/components/work/TranscriptView";
import {
  analyzeCall,
  getLeadCalls,
  transcriptIsMessy,
  type CallRecord,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { showError } from "@/lib/toast";

const OUTCOME_KEYS: Record<string, TranslationKey> = {
  goal: "calls.outcome.goal",
  callback: "calls.outcome.callback",
  thinking: "calls.outcome.thinking",
  no_answer: "calls.outcome.no_answer",
  refused: "calls.outcome.refused",
  wrong_number: "calls.outcome.wrong_number",
};

/**
 * Звонки лида через телефонию. Каждый звонок — строка-аккордеон:
 * дата, кто звонил, длительность и исход видны сразу, запись,
 * разбор ИИ и расшифровка — по клику. Последний звонок раскрыт.
 * Пусто — блок не рисуется: без телефонии или до первого звонка
 * карточке нечего показывать.
 */
export function LeadCalls({
  leadId,
  onCount,
  showTitle = true,
}: {
  leadId: string;
  onCount?: (n: number) => void;
  showTitle?: boolean;
}) {
  const { t } = useLocale();
  const [calls, setCalls] = useState<CallRecord[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [openTranscript, setOpenTranscript] = useState<string | null>(null);

  // Звонки, отправленные на разбор кнопкой, — ждём их оценку.
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set());
  const analyzingRef = useRef(analyzing);
  analyzingRef.current = analyzing;

  const callsRef = useRef<CallRecord[] | null>(null);
  callsRef.current = calls;

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      getLeadCalls(leadId)
        .then((rows) => {
          if (cancelled) return;
          setCalls(rows);
          onCount?.(rows.length);
          setAnalyzing((prev) =>
            prev.size ? new Set([...prev].filter((id) => !rows.find((r) => r.id === id)?.analysis)) : prev,
          );
          setOpen((cur) => cur ?? rows[0]?.id ?? null);
        })
        .catch(() => {
          if (!cancelled) setCalls([]);
        });
    void load();
    // Пока звонок в обработке (набор, запись → текст → разбор по
    // автоматике или по кнопке), подтягиваем раз в 10 секунд.
    const timer = window.setInterval(() => {
      if (
        analyzingRef.current.size > 0 ||
        callsRef.current?.some((c) => c.state === "dialing" || c.processing)
      )
        void load();
    }, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // onCount — колбэк родителя, стабильность не гарантирована.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leadId]);

  const analyzeOne = async (id: string, retranscribe = false) => {
    try {
      await analyzeCall(id, retranscribe);
      setAnalyzing((prev) => new Set(prev).add(id));
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    }
  };

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
        return c.processing || analyzing.has(c.id) ? t("calls.state.processing") : null;
      case "failed":
        return t("calls.state.failed");
      default:
        return null;
    }
  };

  return (
    <div>
      {showTitle && (
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          {t("calls.title")}
        </div>
      )}
      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: 10,
          overflow: "hidden",
        }}
      >
        {calls.map((c, idx) => {
          const a = c.analysis;
          const status = stateLabel(c);
          const isOpen = open === c.id;
          const outcome =
            a?.suggested_outcome && OUTCOME_KEYS[a.suggested_outcome]
              ? t(OUTCOME_KEYS[a.suggested_outcome])
              : null;
          return (
            <div
              key={c.id}
              style={{
                borderTop: idx === 0 ? "none" : "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : c.id)}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: "4px 10px",
                  padding: "9px 12px",
                  background: isOpen ? "var(--surface-2)" : "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                  fontSize: 12.5,
                  color: "var(--text)",
                }}
              >
                <Icon
                  name={isOpen ? "chevronDown" : "chevronRight"}
                  size={13}
                  style={{ color: "var(--text-dim)", flexShrink: 0 }}
                />
                <span style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                  {new Date(c.created_at).toLocaleString("ru-RU", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                {c.user_name && (
                  <span style={{ color: "var(--text-muted)" }}>· {c.user_name}</span>
                )}
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {t("calls.talk", { time: mmss(c.talk_sec) })}
                </span>
                <span style={{ flex: 1, minWidth: 0 }} />
                {status && (
                  <span
                    style={{
                      fontSize: 11.5,
                      color: c.state === "failed" ? "var(--cold)" : "var(--text-muted)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {status}
                  </span>
                )}
                {outcome && (
                  <span
                    className="chip"
                    style={{ fontSize: 11, color: "var(--accent)", borderColor: "var(--accent)" }}
                  >
                    {outcome}
                  </span>
                )}
                {typeof a?.quality_score === "number" && (
                  <span className="chip" style={{ fontSize: 11 }}>
                    {a.quality_score}/10
                  </span>
                )}
                {c.has_recording && (
                  <Icon name="phone" size={12} style={{ color: "var(--text-dim)" }} />
                )}
              </button>

              {isOpen && (
                <div
                  style={{
                    padding: "4px 12px 12px 35px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    background: "var(--surface-2)",
                  }}
                >
                  {c.has_recording && (
                    <RecordingPlayer callId={c.id} />
                  )}

                  {a && (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                        fontSize: 13,
                        lineHeight: 1.5,
                      }}
                    >
                      {a.summary && <div>{a.summary}</div>}
                      {a.next_step && (
                        <div>
                          <b>{t("calls.nextStep")}:</b> {a.next_step}
                        </div>
                      )}
                      {(a.objections ?? []).length > 0 && (
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {(a.objections ?? []).map((o) => (
                            <span
                              key={o}
                              className="chip"
                              style={{ fontSize: 11, color: "var(--warm)", borderColor: "var(--warm)" }}
                            >
                              {o}
                            </span>
                          ))}
                        </div>
                      )}
                      {a.quality_notes && (
                        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          {a.quality_notes}
                        </div>
                      )}
                    </div>
                  )}

                  {a?.too_short && (
                    <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("ca.tooShort")}</div>
                  )}
                  {a?.rubric && a.rubric.length > 0 && <RubricView items={a.rubric} />}
                  {c.has_recording && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ alignSelf: "flex-start" }}
                      disabled={analyzing.has(c.id)}
                      onClick={() => void analyzeOne(c.id)}
                    >
                      <Icon name="sparkles" size={12} />
                      {analyzing.has(c.id) ? t("ca.analyzing") : a && !a.too_short ? t("ca.reanalyze") : t("ca.analyzeOne")}
                    </button>
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
                      {openTranscript === c.id && <TranscriptView segments={c.transcript} />}
                      {openTranscript === c.id && c.has_recording && transcriptIsMessy(c.transcript) && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ alignSelf: "flex-start" }}
                          disabled={analyzing.has(c.id)}
                          onClick={() => void analyzeOne(c.id, true)}
                        >
                          <Icon name="rotateCcw" size={12} /> {t("ca.retranscribe")}
                        </button>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
