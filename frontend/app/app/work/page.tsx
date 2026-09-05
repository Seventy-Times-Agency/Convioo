"use client";

import Link from "next/link";
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
  getTeamHome,
  getWorkQueue,
  postCallOutcome,
  type CallOutcome,
  type Funnel,
  type Lead,
  type QueueLead,
  type TeamHome,
  type WorkQueue,
} from "@/lib/api";
import { getTeamDetail } from "@/lib/api";
import { TeamCallDesk } from "@/components/work/TeamCallDesk";
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
  // Счётчики шапки «Наборы · Разговоры · Цели» — те же, что на
  // главной селза, поэтому берём их из одного источника.
  const [counters, setCounters] = useState<TeamHome | null>(null);
  // Роль решает текст пустой очереди: руководителю — «раздайте в
  // CRM», селзу — «менеджер ещё не распределил пакет».
  const [myRole, setMyRole] = useState<string | null>(null);
  // Руководитель по умолчанию видит пульт отдела, а не звонилку;
  // «Мой прозвон» — для тимлида, который звонит и сам.
  const [deskMode, setDeskMode] = useState(true);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  useEffect(
    () =>
      subscribeWorkspace(() => {
        const w = getActiveWorkspace();
        setTeamId(w.kind === "team" ? w.team_id : null);
      }),
    [],
  );

  useEffect(() => {
    if (!teamId) {
      setMyRole(null);
      return;
    }
    getTeamDetail(teamId)
      .then((d) => setMyRole(d.role))
      .catch(() => setMyRole(null));
  }, [teamId]);

  const reloadQueue = useCallback(() => {
    if (!teamId) {
      setQueue(null);
      return;
    }
    getWorkQueue(teamId)
      .then(setQueue)
      .catch((e) => showError(toMessage(e)));
    // Счётчики дня — не критичны для работы экрана, поэтому их
    // ошибку не показываем: очередь важнее.
    getTeamHome(teamId)
      .then(setCounters)
      .catch(() => undefined);
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
      <div className="page" style={{ maxWidth: 1500 }}>
        {/* Вкладки из макета: прозвон и письма — две стороны одной
            работы селза. */}
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          <span className="btn btn-primary btn-sm">
            {t("letters.tabCalls")}
          </span>
          <Link href="/app/work/letters" className="btn btn-ghost btn-sm">
            {t("letters.tabLetters")}
          </Link>
          {myRole && myRole !== "sales" && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ marginLeft: "auto" }}
              onClick={() => setDeskMode((v) => !v)}
            >
              {deskMode ? t("desk.myCalls") : t("desk.backToDesk")}
            </button>
          )}
        </div>

        {myRole && myRole !== "sales" && deskMode ? (
          <TeamCallDesk teamId={teamId} />
        ) : (
        <>
        {/* Шапка прозвона из макета: счёт дня. «Разговоры» — наборы,
            где сняли трубку. Длительности у нас нет, поэтому «2+ мин»
            из макета не считается — телефония ещё не подключена. */}
        {counters && (
          <div
            style={{
              display: "flex",
              gap: 22,
              alignItems: "baseline",
              flexWrap: "wrap",
              marginBottom: 14,
              paddingBottom: 12,
              borderBottom: "1px solid var(--border)",
            }}
          >
            {(
              [
                [t("work.cntDials"), counters.dials_today],
                [t("work.cntTalks"), counters.conversations_today],
                [t("work.cntGoals"), counters.goals_today],
              ] as const
            ).map(([label, value]) => (
              <div key={label} style={{ display: "flex", gap: 7, alignItems: "baseline" }}>
                <span
                  style={{
                    fontSize: 9.5,
                    fontWeight: 800,
                    letterSpacing: "0.09em",
                    textTransform: "uppercase",
                    color: "var(--text-dim)",
                  }}
                >
                  {label}
                </span>
                <span
                  style={{
                    fontSize: 16,
                    fontWeight: 800,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>
        )}
        {queue !== null && queue.total === 0 && (
          <Card>
            <EmptyState
              icon={<Icon name="zap" size={20} />}
              title={t("work.emptyTitle")}
              hint={
                myRole && myRole !== "sales"
                  ? t("work.emptyHintManager")
                  : t("work.emptyHint")
              }
            />
            {myRole && myRole !== "sales" && (
              <div style={{ textAlign: "center", marginTop: 4 }}>
                <Link href="/app/leads" className="btn btn-primary btn-sm">
                  {t("work.emptyOpenCrm")}
                </Link>
              </div>
            )}
          </Card>
        )}
        {(queue === null || queue.total > 0) && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "262px minmax(0, 1fr) 306px",
            gap: 16,
            alignItems: "start",
          }}
        >
          {/* Очередь */}
          <Card padding={14}>
            {queue === null && <SkeletonLines lines={6} />}
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

                  {/* Факты под заходом — четыре колонки, как в макете.
                      Вместо «оценки бюджета» показываем язык бизнеса:
                      бюджет ниоткуда не считается, а язык решает, на
                      каком языке звонить. */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                      gap: 9,
                      marginBottom: 14,
                    }}
                  >
                    {(
                      [
                        [
                          t("work.factReviews"),
                          lead.rating != null
                            ? `${lead.reviews_count ?? 0} · ${lead.rating}`
                            : "—",
                        ],
                        [
                          t("work.factSite"),
                          lead.website ? t("common.yes") : t("common.no"),
                        ],
                        [
                          t("work.factSocial"),
                          lead.social_links &&
                          Object.keys(lead.social_links).length > 0
                            ? Object.keys(lead.social_links).length.toString()
                            : "—",
                        ],
                        [
                          t("work.factLang"),
                          lead.business_language
                            ? lead.business_language.toUpperCase()
                            : "—",
                        ],
                      ] as const
                    ).map(([label, value]) => (
                      <div
                        key={label}
                        style={{
                          border: "1px solid var(--border)",
                          borderRadius: 9,
                          padding: "8px 10px",
                          minWidth: 0,
                        }}
                      >
                        <div
                          style={{
                            fontSize: 9,
                            fontWeight: 800,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--text-dim)",
                          }}
                        >
                          {label}
                        </div>
                        <div
                          style={{
                            fontSize: 14,
                            fontWeight: 700,
                            marginTop: 2,
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {value}
                        </div>
                      </div>
                    ))}
                  </div>

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

                  {/* Скрипт, возражения и заметка живут в правой
                      панели — см. третью колонку ниже. */}

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
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
                          gap: 8,
                          width: "100%",
                          // Без nowrap: название целевого действия
                          // приходит из воронки и бывает длинным
                          // («Платный аудит»), а колонок ровно шесть —
                          // пусть переносится, но не обрезается.
                          textAlign: "center",
                        }}
                      >
                        <Button
                          className="btn-outcome"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("no_answer")}
                        >
                          {t("work.oNoAnswer")}
                        </Button>
                        <Button
                          className="btn-outcome"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("wrong_number")}
                        >
                          {t("work.oWrongNumber")}
                        </Button>
                        <Button
                          className="btn-outcome"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("refused")}
                        >
                          {t("work.oRefused")}
                        </Button>
                        <Button
                          className="btn-outcome"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("thinking")}
                        >
                          {t("work.oThinking")}
                        </Button>
                        <Button
                          className="btn-outcome"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => setCallbackPick(true)}
                        >
                          {t("work.oCallback")}
                        </Button>
                        <Button
                          className="btn-outcome"
                          size="sm"
                          disabled={busy}
                          onClick={() => applyOutcome("goal")}
                        >
                          {funnel?.goal_name ?? t("work.oGoalFallback")}
                        </Button>
                      </div>
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

          {/* Третья панель макета: то, что «загружает менеджер»
              (скрипт и возражения воронки), плюс заметка к звонку. */}
          {currentId && (
            <Card padding={14}>
              <div className="eyebrow" style={{ marginBottom: 8 }}>
                {t("work.scriptTitle")}
                {funnel ? ` · ${funnel.name}` : ""}
              </div>
              {funnel?.script ? (
                <ol
                  style={{
                    margin: 0,
                    paddingLeft: 18,
                    fontSize: 12.5,
                    lineHeight: 1.55,
                    color: "var(--text-muted)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  {funnel.script
                    .split("\n")
                    .map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim())
                    .filter(Boolean)
                    .map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                </ol>
              ) : (
                <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                  {t("work.scriptEmpty")}
                </div>
              )}

              {funnel?.objections && funnel.objections.length > 0 && (
                <>
                  <div
                    className="eyebrow"
                    style={{ margin: "16px 0 8px" }}
                  >
                    {t("work.objectionsTitle")}
                  </div>
                  {funnel.objections.map((o, i) => (
                    <div
                      key={i}
                      style={{
                        paddingBottom: 8,
                        marginBottom: 8,
                        borderBottom:
                          i === funnel.objections!.length - 1
                            ? "none"
                            : "1px solid var(--border)",
                      }}
                    >
                      <div style={{ fontSize: 12.5, fontWeight: 700 }}>
                        «{o.objection}»
                      </div>
                      <div
                        style={{
                          fontSize: 12.5,
                          color: "var(--text-muted)",
                          lineHeight: 1.5,
                          marginTop: 2,
                        }}
                      >
                        — {o.answer}
                      </div>
                    </div>
                  ))}
                </>
              )}

              <div style={{ marginTop: 16 }}>
                <Textarea
                  ref={noteRef}
                  label={t("work.noteLabel")}
                  rows={phase === "during" ? 7 : 4}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder={t("work.notePh")}
                />
              </div>
            </Card>
          )}

        </div>
        )}
        </>
        )}
      </div>
    </>
  );
}
