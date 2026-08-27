"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  SkeletonLines,
  Textarea,
} from "@/components/ui";
import {
  getLead,
  getLeadFunnel,
  getWorkQueue,
  postCallOutcome,
  type CallOutcome,
  type Funnel,
  type Lead,
  type QueueLead,
  type WorkQueue,
} from "@/lib/api";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

/** Работа — режим прозвона: очередь (перезвоны → горячие → остальные)
 * → карточка лида → звонок в один клик → исход одной кнопкой.
 * Три состояния экрана: до / во время (таймер, заметка в фокусе,
 * исходы неактивны) / после (исход порождает следующее касание). */

type Phase = "before" | "during" | "after";

function toMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function fmtTimer(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function WorkPage() {
  const { t } = useLocale();
  const [teamId, setTeamId] = useState<string | null>(() => {
    const w = getActiveWorkspace();
    return w.kind === "team" ? w.team_id : null;
  });
  const [queue, setQueue] = useState<WorkQueue | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [lead, setLead] = useState<Lead | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [phase, setPhase] = useState<Phase>("before");
  const [seconds, setSeconds] = useState(0);
  const [note, setNote] = useState("");
  const [tab, setTab] = useState<"summary" | "analysis" | "reviews" | "site">(
    "summary",
  );
  const [busy, setBusy] = useState(false);
  const [callbackPick, setCallbackPick] = useState(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  useEffect(
    () =>
      subscribeWorkspace(() => {
        const w = getActiveWorkspace();
        setTeamId(w.kind === "team" ? w.team_id : null);
      }),
    [],
  );

  const reloadQueue = useCallback(() => {
    if (!teamId) {
      setQueue(null);
      return;
    }
    getWorkQueue(teamId)
      .then(setQueue)
      .catch((e) => showError(toMessage(e)));
  }, [teamId]);

  useEffect(() => {
    setQueue(null);
    setCurrentId(null);
    reloadQueue();
  }, [reloadQueue]);

  const flat: QueueLead[] = useMemo(
    () =>
      queue ? [...queue.callbacks, ...queue.hot, ...queue.rest] : [],
    [queue],
  );

  // Автовыбор первого лида очереди.
  useEffect(() => {
    if (!currentId && flat.length > 0) setCurrentId(flat[0].id);
  }, [flat, currentId]);

  // Загрузка карточки + воронки выбранного лида.
  useEffect(() => {
    if (!currentId) {
      setLead(null);
      setFunnel(null);
      return;
    }
    setLead(null);
    setFunnel(null);
    setPhase("before");
    setSeconds(0);
    setNote("");
    setTab("summary");
    setCallbackPick(false);
    getLead(currentId)
      .then(setLead)
      .catch((e) => showError(toMessage(e)));
    getLeadFunnel(currentId)
      .then(setFunnel)
      .catch(() => setFunnel(null));
  }, [currentId]);

  // Таймер разговора.
  useEffect(() => {
    if (phase !== "during") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  const startCall = () => {
    setPhase("during");
    setSeconds(0);
    setTimeout(() => noteRef.current?.focus(), 50);
    if (lead?.phone) {
      window.location.href = `tel:${lead.phone.replace(/[^+\d]/g, "")}`;
    }
  };

  const finishCall = () => setPhase("after");

  const applyOutcome = async (
    outcome: CallOutcome,
    callbackAt?: string,
  ) => {
    if (!currentId || busy) return;
    setBusy(true);
    try {
      const r = await postCallOutcome(currentId, outcome, {
        callbackAt,
        note: note.trim() || undefined,
      });
      if (outcome === "goal") {
        showSuccess(
          t("work.goalToast", {
            goal: String(r.result.goal_name ?? funnel?.goal_name ?? ""),
          }),
        );
      }
      // Следующий лид очереди.
      const idx = flat.findIndex((x) => x.id === currentId);
      const next = flat[idx + 1]?.id ?? null;
      setCurrentId(next);
      reloadQueue();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const callbackChips: { label: string; hours: number }[] = [
    { label: t("work.cb2h"), hours: 2 },
    { label: t("work.cbTomorrow"), hours: 24 },
    { label: t("work.cb3d"), hours: 72 },
  ];

  const currentStepIndex = useMemo(() => {
    if (!funnel || !lead) return 0;
    // funnel_step живёт на бэке; на карточке показываем позицию по
    // порядку шагов относительно «звонок сейчас».
    return Math.min(
      funnel.steps.length - 1,
      Math.max(0, funnel.steps.findIndex((s) => s.kind === "call")),
    );
  }, [funnel, lead]);

  if (!teamId) {
    return (
      <>
        <Topbar crumbs={[{ label: t("nav.work") }]} />
        <div className="page">
          <Card>
            <EmptyState
              icon={<Icon name="zap" size={20} />}
              title={t("funnels.noTeamTitle")}
              hint={t("work.noTeamHint")}
            />
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar crumbs={[{ label: t("nav.work") }]} />
      <div className="page" style={{ maxWidth: 1400 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "260px 1fr",
            gap: 20,
            alignItems: "start",
          }}
        >
          {/* Очередь */}
          <Card padding={14}>
            {queue === null && <SkeletonLines lines={6} />}
            {queue !== null && queue.total === 0 && (
              <EmptyState
                icon={<Icon name="zap" size={18} />}
                title={t("work.emptyTitle")}
                hint={t("work.emptyHint")}
              />
            )}
            {queue !== null && queue.total > 0 && (
              <>
                {(
                  [
                    ["callbacks", t("work.qCallbacks")],
                    ["hot", t("work.qHot")],
                    ["rest", t("work.qRest")],
                  ] as const
                ).map(([key, label]) => {
                  const items = queue[key];
                  if (items.length === 0) return null;
                  return (
                    <div key={key} style={{ marginBottom: 12 }}>
                      <div
                        className="eyebrow"
                        style={{ marginBottom: 6 }}
                      >
                        {label} · {items.length}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 4,
                        }}
                      >
                        {items.map((q) => (
                          <button
                            key={q.id}
                            type="button"
                            onClick={() => setCurrentId(q.id)}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: 8,
                              padding: "7px 10px",
                              borderRadius: 8,
                              border: "1px solid",
                              borderColor:
                                q.id === currentId
                                  ? "var(--accent)"
                                  : "transparent",
                              background:
                                q.id === currentId
                                  ? "var(--accent-soft)"
                                  : "transparent",
                              cursor: "pointer",
                              fontSize: 13,
                              textAlign: "left",
                            }}
                          >
                            <span
                              style={{
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {q.name}
                            </span>
                            <span
                              style={{
                                color: "var(--text-dim)",
                                fontSize: 11.5,
                                flexShrink: 0,
                              }}
                            >
                              {key === "callbacks" && q.next_touch_at
                                ? new Date(
                                    q.next_touch_at,
                                  ).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : (q.score ?? "")}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </Card>

          {/* Карточка лида */}
          {currentId && (
            <Card>
              {!lead && <SkeletonLines lines={8} />}
              {lead && (
                <>
                  {/* Шапка */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                      alignItems: "flex-start",
                      marginBottom: 14,
                      flexWrap: "wrap",
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 19, fontWeight: 800 }}>
                        {lead.name}
                      </div>
                      <div
                        style={{
                          fontSize: 13,
                          color: "var(--text-muted)",
                          marginTop: 3,
                        }}
                      >
                        {[lead.category, lead.address]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      {typeof lead.score_ai === "number" && (
                        <Chip
                          tone={
                            lead.score_ai >= 75 ? "positive" : "default"
                          }
                        >
                          {Math.round(lead.score_ai)}
                        </Chip>
                      )}
                      {phase === "during" && (
                        <Chip tone="problem">
                          ● REC · {fmtTimer(seconds)}
                        </Chip>
                      )}
                    </div>
                  </div>

                  {/* Заход от ИИ */}
                  {lead.advice && (
                    <div
                      style={{
                        padding: "12px 14px",
                        borderRadius: 10,
                        background: "var(--accent-soft)",
                        border:
                          "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
                        fontSize: 13.5,
                        lineHeight: 1.55,
                        marginBottom: 14,
                      }}
                    >
                      <div
                        className="eyebrow"
                        style={{ marginBottom: 4, color: "var(--accent)" }}
                      >
                        {t("work.opener")}
                      </div>
                      {lead.advice}
                    </div>
                  )}

                  {/* Вкладки */}
                  <div className="seg" style={{ marginBottom: 12 }}>
                    {(
                      [
                        ["summary", t("work.tabSummary")],
                        ["analysis", t("work.tabAnalysis")],
                        ["reviews", t("work.tabReviews")],
                        ["site", t("work.tabSite")],
                      ] as const
                    ).map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        className={tab === key ? "active" : ""}
                        onClick={() => setTab(key)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div
                    style={{
                      fontSize: 13.5,
                      lineHeight: 1.6,
                      color: "var(--text)",
                      marginBottom: 16,
                      minHeight: 60,
                    }}
                  >
                    {tab === "summary" &&
                      (lead.summary || t("work.noData"))}
                    {tab === "analysis" && (
                      <div>
                        {(lead.strengths ?? []).map((s, i) => (
                          <div key={`s${i}`}>+ {s}</div>
                        ))}
                        {(lead.weaknesses ?? []).map((w, i) => (
                          <div key={`w${i}`} style={{ color: "var(--warm)" }}>
                            − {w}
                          </div>
                        ))}
                        {(lead.red_flags ?? []).map((r, i) => (
                          <div key={`r${i}`} style={{ color: "var(--cold)" }}>
                            ! {r}
                          </div>
                        ))}
                        {!lead.strengths?.length &&
                          !lead.weaknesses?.length &&
                          t("work.noData")}
                      </div>
                    )}
                    {tab === "reviews" &&
                      (lead.rating != null
                        ? `${lead.rating} ★ · ${lead.reviews_count ?? 0} ${t(
                            "work.reviewsCount",
                          )}`
                        : t("work.noData"))}
                    {tab === "site" && (
                      <div>
                        {lead.website ? (
                          <a
                            href={lead.website}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {lead.website}
                          </a>
                        ) : (
                          t("work.noSite")
                        )}
                        {lead.social_links &&
                          Object.entries(lead.social_links).map(([k, v]) => (
                            <div key={k}>
                              <a href={v} target="_blank" rel="noreferrer">
                                {k}
                              </a>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>

                  {/* Путь касаний */}
                  {funnel && (
                    <div style={{ marginBottom: 16 }}>
                      <div className="eyebrow" style={{ marginBottom: 6 }}>
                        {t("work.pathTitle")} · {funnel.name}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          gap: 6,
                          flexWrap: "wrap",
                          fontSize: 12.5,
                        }}
                      >
                        {funnel.steps.map((s, i) => (
                          <Chip
                            key={i}
                            tone={i === currentStepIndex ? "accent" : "default"}
                          >
                            {i + 1} ·{" "}
                            {s.kind === "call"
                              ? t("funnels.stepCall")
                              : t("funnels.stepEmail")}
                            {s.day_offset > 0 ? ` +${s.day_offset}д` : ""}
                          </Chip>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Скрипт */}
                  {funnel?.script && (
                    <details style={{ marginBottom: 16 }}>
                      <summary
                        style={{
                          cursor: "pointer",
                          fontSize: 13,
                          fontWeight: 600,
                          color: "var(--accent)",
                        }}
                      >
                        {t("work.scriptTitle")}
                      </summary>
                      <div
                        style={{
                          whiteSpace: "pre-wrap",
                          fontSize: 13,
                          lineHeight: 1.6,
                          padding: "10px 0",
                          color: "var(--text-muted)",
                        }}
                      >
                        {funnel.script}
                      </div>
                    </details>
                  )}

                  {/* Заметка */}
                  <Textarea
                    ref={noteRef}
                    label={t("work.noteLabel")}
                    rows={phase === "during" ? 5 : 2}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder={t("work.notePh")}
                  />

                  {/* Действия по состояниям */}
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      flexWrap: "wrap",
                      marginTop: 16,
                      alignItems: "center",
                    }}
                  >
                    {phase === "before" && (
                      <>
                        <Button onClick={startCall} disabled={!lead.phone}>
                          <Icon name="zap" size={14} />
                          {t("work.callButton")}
                          {lead.phone ? ` · ${lead.phone}` : ""}
                        </Button>
                        <span
                          style={{
                            fontSize: 12,
                            color: "var(--text-dim)",
                          }}
                        >
                          {t("work.recNote")}
                        </span>
                      </>
                    )}
                    {phase === "during" && (
                      <>
                        <Button variant="ghost" onClick={finishCall}>
                          {t("work.finishCall")} · {fmtTimer(seconds)}
                        </Button>
                        <span
                          style={{ fontSize: 12, color: "var(--text-dim)" }}
                        >
                          {t("work.duringHint")}
                        </span>
                      </>
                    )}
                    {phase === "after" && !callbackPick && (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("no_answer")}
                        >
                          {t("work.oNoAnswer")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("wrong_number")}
                        >
                          {t("work.oWrongNumber")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("refused")}
                        >
                          {t("work.oRefused")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("thinking")}
                        >
                          {t("work.oThinking")}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => setCallbackPick(true)}
                        >
                          {t("work.oCallback")}
                        </Button>
                        <Button
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("goal")}
                        >
                          {funnel?.goal_name ?? t("work.oGoalFallback")}
                        </Button>
                      </>
                    )}
                    {phase === "after" && callbackPick && (
                      <>
                        <span style={{ fontSize: 13 }}>
                          {t("work.cbWhen")}
                        </span>
                        {callbackChips.map((c) => (
                          <Button
                            key={c.hours}
                            variant="soft"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              applyOutcome(
                                "callback",
                                new Date(
                                  Date.now() + c.hours * 3600_000,
                                ).toISOString(),
                              )
                            }
                          >
                            {c.label}
                          </Button>
                        ))}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setCallbackPick(false)}
                        >
                          {t("common.cancel")}
                        </Button>
                      </>
                    )}
                  </div>
                  {funnel && phase === "after" && (
                    <div
                      style={{
                        fontSize: 11.5,
                        color: "var(--text-dim)",
                        marginTop: 10,
                      }}
                    >
                      {t("work.footnote", {
                        n: funnel.no_answer_attempts,
                        d: funnel.no_answer_pause_days,
                      })}
                    </div>
                  )}
                </>
              )}
            </Card>
          )}

          {!currentId && queue !== null && queue.total === 0 && (
            <Card>
              <EmptyState
                icon={<Icon name="zap" size={20} />}
                title={t("work.emptyTitle")}
                hint={t("work.emptyHint")}
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
