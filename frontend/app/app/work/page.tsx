"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/brand/Icon";
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
import {
  assignLeadsToFunnel,
  listFunnels,
  getTeamDetail,
  getTelephonyStatus,
  setCallConsent,
  startProviderCall,
  type TelephonyStatus,
} from "@/lib/api";
import { LeadCalls } from "@/components/leads/LeadCalls";
import { TeamCallDesk } from "@/components/work/TeamCallDesk";
import { WorkModeSwitch } from "@/components/work/WorkModeSwitch";
import { fillLine, parseScript } from "@/lib/script";
import { getActiveWorkspace, subscribeWorkspace } from "@/lib/workspace";
import {
  microphoneAvailable,
  placeBrowserCall,
  type BrowserCallHandle,
  type BrowserCallState,
} from "@/lib/telephony/browserCall";
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
  // Воронки команды — селз или тимлид выбирает, по какой вести лида
  // (только звонки / звонки и письма).
  const [funnels, setFunnels] = useState<Funnel[]>([]);
  const [phase, setPhase] = useState<Phase>("before");
  const [seconds, setSeconds] = useState(0);
  const [note, setNote] = useState("");
  const [tab, setTab] = useState<"summary" | "analysis" | "history" | "site">(
    "summary",
  );
  const [rightTab, setRightTab] = useState<"script" | "objections" | "note">("script");
  const [queueOpen, setQueueOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  // Момент успеха: зелёная плашка с галочкой рядом с кнопкой звонка.
  const [celebrate, setCelebrate] = useState<{ text: string; at: number } | null>(null);
  useEffect(() => {
    if (!celebrate) return;
    const id = setTimeout(() => setCelebrate(null), 2600);
    return () => clearTimeout(id);
  }, [celebrate]);
  const [callbackPick, setCallbackPick] = useState(false);
  // Счётчики шапки «Наборы · Разговоры · Цели» — те же, что на
  // главной селза, поэтому берём их из одного источника.
  const [counters, setCounters] = useState<TeamHome | null>(null);
  // Роль решает текст пустой очереди: руководителю — «раздайте в
  // CRM», селзу — «менеджер ещё не распределил пакет».
  const [myRole, setMyRole] = useState<string | null>(null);
  const [telephony, setTelephony] = useState<TelephonyStatus | null>(null);
  // Текущий звонок через провайдера и согласие клиента на запись.
  const [providerCallId, setProviderCallId] = useState<string | null>(null);
  const [recording, setRecording] = useState(true);
  // Звонок из вкладки (Telnyx): состояние соединения и микрофон.
  const [browserState, setBrowserState] = useState<BrowserCallState | null>(null);
  const [muted, setMuted] = useState(false);
  const browserCall = useRef<BrowserCallHandle | null>(null);
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

  const activeTeamRef = useRef<string | null>(teamId);
  activeTeamRef.current = teamId;

  useEffect(() => {
    if (!teamId) {
      setMyRole(null);
      return;
    }
    // При смене команды ответы по прежней не должны перезаписать новую.
    let stale = false;
    getTeamDetail(teamId)
      .then((d) => !stale && setMyRole(d.role))
      .catch(() => !stale && setMyRole(null));
    getTelephonyStatus(teamId)
      .then((tel) => !stale && setTelephony(tel))
      .catch(() => !stale && setTelephony(null));
    listFunnels(teamId)
      .then((rows) => !stale && setFunnels(rows.filter((f) => f.status !== "archived")))
      .catch(() => !stale && setFunnels([]));
    return () => {
      stale = true;
    };
  }, [teamId]);

  const switchFunnel = async (funnelId: string) => {
    if (!currentId || !funnelId) return;
    try {
      await assignLeadsToFunnel(funnelId, [currentId]);
      const next = await getLeadFunnel(currentId);
      setFunnel(next);
      showSuccess(t("work.funnelSwitched"));
    } catch (e) {
      showError(toMessage(e));
    }
  };

  const reloadQueue = useCallback(() => {
    if (!teamId) {
      setQueue(null);
      return;
    }
    // Очередь прежней команды не должна перезаписать новую.
    const forTeam = teamId;
    getWorkQueue(teamId)
      .then((q) => {
        if (activeTeamRef.current === forTeam) setQueue(q);
      })
      .catch((e) => showError(toMessage(e)));
    // Счётчики дня — не критичны для работы экрана, поэтому их
    // ошибку не показываем: очередь важнее.
    getTeamHome(teamId)
      .then((c) => {
        if (activeTeamRef.current === forTeam) setCounters(c);
      })
      .catch(() => undefined);
  }, [teamId]);

  // «Позвонить» из карточки в CRM открывает /app/work?lead=<id>: лид
  // показываем сразу, даже если его нет в очереди (закрыт, назначен
  // на потом) — до клиента должно быть можно добраться всегда.
  const pinnedLead = useRef<string | null>(
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("lead"),
  );

  useEffect(() => {
    setQueue(null);
    setCurrentId(pinnedLead.current);
    if (pinnedLead.current) setDeskMode(false);
    reloadQueue();
  }, [reloadQueue]);

  // «Позже» в общий обход не входит: после исхода переходим только по
  // тем, кого пора набирать сейчас.
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
    setRightTab("script");
    setCallbackPick(false);
    // Ответ по прошлому лиду может прийти позже нового: без этой
    // отметки карточка показала бы лида X, а исход ушёл бы лиду Y.
    let stale = false;
    getLead(currentId)
      .then((l) => {
        if (!stale) setLead(l);
      })
      .catch((e) => {
        if (!stale) showError(toMessage(e));
      });
    getLeadFunnel(currentId)
      .then((f) => {
        if (!stale) setFunnel(f);
      })
      .catch(() => {
        if (!stale) setFunnel(null);
      });
    return () => {
      stale = true;
    };
  }, [currentId]);

  // Таймер разговора.
  useEffect(() => {
    if (phase !== "during") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  const startCall = async () => {
    setPhase("during");
    setSeconds(0);
    setMuted(false);
    setBrowserState(null);
    setTimeout(() => noteRef.current?.focus(), 50);
    if (!lead?.phone) return;
    // Звонок из вкладки: провайдер в режиме браузера и микрофон
    // доступен — набираем через WebRTC, разговор пишется у провайдера.
    if (telephony?.enabled && telephony.mode === "browser" && teamId) {
      if (!(await microphoneAvailable())) {
        showError(t("work.noMicrophone"));
      } else {
        try {
          const r = await startProviderCall(lead.id);
          setProviderCallId(r.call_id);
          setRecording(true);
          setBrowserState("connecting");
          browserCall.current = await placeBrowserCall({
            teamId,
            destination: r.destination ?? lead.phone,
            callerNumber: r.caller_number ?? telephony.caller_number,
            onState: (s) => {
              setBrowserState(s);
              if (s === "ended") {
                browserCall.current = null;
                setPhase((p) => (p === "during" ? "after" : p));
              }
            },
          });
          return;
        } catch (e) {
          setBrowserState("failed");
          showError(toMessage(e));
        }
      }
    }
    // Провайдер звонит сотруднику первым (Ringostat) — нужен его
    // номер; иначе — как раньше, tel: на устройстве.
    if (telephony?.enabled && telephony.mode === "callback" && telephony.my_extension) {
      try {
        const r = await startProviderCall(lead.id);
        setProviderCallId(r.call_id);
        setRecording(true);
        showSuccess(t("work.providerCalling"));
        return;
      } catch (e) {
        showError(toMessage(e));
      }
    }
    window.location.href = `tel:${lead.phone.replace(/[^+\d]/g, "")}`;
  };

  const finishCall = () => {
    browserCall.current?.hangup();
    browserCall.current = null;
    setPhase("after");
  };

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    browserCall.current?.mute(next);
  };

  // Клиент против записи — «Отменить запись»; передумал — включить
  // обратно. Отказ стирает у нас всё, что уже успело сохраниться.
  const toggleRecording = async () => {
    if (!providerCallId) return;
    const next = !recording;
    setRecording(next);
    try {
      await setCallConsent(providerCallId, next);
      showSuccess(next ? t("work.recOnToast") : t("work.recOffToast"));
    } catch (e) {
      setRecording(!next);
      showError(toMessage(e));
    }
  };

  // Фраза-предупреждение на языке клиента: украинский номер —
  // по-украински, остальные — по-английски.
  const consentPhrase = (phone: string | null | undefined) =>
    (phone ?? "").replace(/[^\d]/g, "").startsWith("380") ||
    (phone ?? "").replace(/[^\d]/g, "").startsWith("0")
      ? t("work.consentUa")
      : t("work.consentEn");

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
        setCelebrate({
          text: t("work.goalToast", {
            goal: String(r.result.goal_name ?? funnel?.goal_name ?? ""),
          }),
          at: Date.now(),
        });
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

  // Горячие клавиши исходов после звонка; в полях ввода не работают.
  useEffect(() => {
    if (phase !== "after") return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.tagName === "SELECT")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      const map: Record<string, CallOutcome | "cb"> = {
        g: "goal", п: "goal",
        c: "cb", с: "cb",
        t: "thinking", е: "thinking",
        n: "no_answer", т: "no_answer",
        r: "refused", к: "refused",
        w: "wrong_number", ц: "wrong_number",
      };
      const o = map[k];
      if (!o) return;
      e.preventDefault();
      if (o === "cb") setCallbackPick(true);
      else void applyOutcome(o);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, currentId, busy, note]);

  const sections = useMemo(() => parseScript(funnel?.script), [funnel?.script]);
  const dm = lead?.website_meta?.contact_person ?? null;
  const placeholders = useMemo(
    () => ({
      contactName: dm?.name?.split(/\s+/)[0] ?? null,
      company: lead?.name ?? null,
      pain: lead?.weaknesses?.[0] ?? null,
    }),
    [dm?.name, lead?.name, lead?.weaknesses],
  );
  const flatIdx = flat.findIndex((x) => x.id === currentId);
  const nextLead = flatIdx >= 0 ? flat[flatIdx + 1] : undefined;

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

  const factBox = (label: string, value: React.ReactNode) => (
    <div style={{ border: "1px solid var(--border)", borderRadius: 9, padding: "8px 10px", minWidth: 0 }}>
      <div style={{ fontSize: 9, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-dim)" }}>
        {label}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {value}
      </div>
    </div>
  );

  const queueRow = (q: QueueLead, bucket: keyof WorkQueue) => (
    <button
      key={q.id}
      type="button"
      onClick={() => setCurrentId(q.id)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        width: "100%",
        padding: "7px 10px",
        borderRadius: 8,
        border: "1px solid " + (q.id === currentId ? "var(--accent)" : "transparent"),
        background: q.id === currentId ? "var(--accent-soft)" : "transparent",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 600,
        textAlign: "left",
        color: "var(--text)",
      }}
    >
      {q.id === currentId && (
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }} />
      )}
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{q.name}</span>
      <span style={{ marginLeft: "auto", color: bucket === "hot" ? "var(--hot)" : "var(--text-dim)", fontSize: 11.5, flexShrink: 0 }}>
        {bucket === "callbacks" && q.next_touch_at
          ? new Date(q.next_touch_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          : bucket === "later" && q.next_touch_at
            ? new Date(q.next_touch_at).toLocaleDateString([], { day: "numeric", month: "short" })
            : (q.score ?? "")}
      </span>
    </button>
  );

  const outcomeBtn = (
    label: string,
    key: string,
    onClick: () => void,
    primary = false,
  ) => (
    <button
      type="button"
      className={primary ? "btn btn-sm m-ring" : "btn btn-ghost btn-sm"}
      disabled={busy}
      onClick={onClick}
      style={{ gap: 6 }}
    >
      <span className="kbd" style={{ fontSize: 10, padding: "0 5px" }}>{key}</span>
      {label}
    </button>
  );

  return (
    <>
      <Topbar
        crumbs={[{ label: t("nav.work") }]}
        right={
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {myRole && myRole !== "sales" && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDeskMode((v) => !v)}>
                {deskMode ? t("desk.myCalls") : t("desk.backToDesk")}
              </button>
            )}
            <WorkModeSwitch mode="calls" />
          </div>
        }
      />
      <div className="page" style={{ maxWidth: 1500, display: "flex", flexDirection: "column", gap: 12 }}>
        {telephony?.enabled && telephony.mode === "callback" && !telephony.my_extension && (
          <div
            role="alert"
            style={{
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
              padding: "10px 14px",
              borderRadius: 10,
              border: "1px solid var(--warning, #9A6B12)",
              background: "rgba(154, 107, 18, 0.08)",
              fontSize: 13,
            }}
          >
            <span style={{ flex: 1, minWidth: 220 }}>{t("work.noExtensionWarn")}</span>
            <Link href="/app/profile" className="btn btn-primary btn-sm">
              {t("work.noExtensionCta")}
            </Link>
          </div>
        )}

        {myRole && myRole !== "sales" && deskMode ? (
          <TeamCallDesk teamId={teamId} />
        ) : (
          <>
            {/* Шапка: счёт дня + воронка */}
            <div style={{ display: "flex", alignItems: "center", gap: 22, flexWrap: "wrap" }}>
              {counters &&
                (
                  [
                    [t("work.cntDials"), counters.dials_today],
                    [t("work.cntTalks"), counters.conversations_today],
                    [t("work.cntGoals"), counters.goals_today],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} style={{ display: "flex", gap: 7, alignItems: "baseline" }}>
                    <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.09em", textTransform: "uppercase", color: "var(--text-dim)" }}>
                      {label}
                    </span>
                    <span style={{ fontSize: 16, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{value}</span>
                  </div>
                ))}
              {funnels.length > 0 && currentId && (
                <select
                  className="select"
                  value={funnel?.id ?? ""}
                  onChange={(e) => void switchFunnel(e.target.value)}
                  style={{ fontSize: 12, padding: "4px 8px", width: "auto", maxWidth: 420, marginLeft: "auto" }}
                  title={t("work.pickFunnel")}
                >
                  {!funnel && <option value="">{t("work.pickFunnel")}</option>}
                  {funnels.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {queue !== null && queue.total === 0 && !currentId && (
              <Card>
                <EmptyState
                  icon={<Icon name="zap" size={20} />}
                  title={t("work.emptyTitle")}
                  hint={myRole && myRole !== "sales" ? t("work.emptyHintManager") : t("work.emptyHint")}
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

            {(queue === null || queue.total > 0 || currentId) && (
              <div className="work-grid">
                {/* ── левая колонка: очередь + клиент ── */}
                <div className="work-left" style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
                  <Card padding={12}>
                    {queue === null && <SkeletonLines lines={4} />}
                    {queue !== null && (
                      <>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                          <span className="eyebrow">
                            {t("work.queue")} · {flatIdx >= 0 ? `${flatIdx + 1} ${t("work.of")} ${flat.length}` : flat.length}
                          </span>
                          <span className="chip" style={{ marginLeft: "auto", fontSize: 11 }}>
                            {t("work.qCallbacks").toLowerCase()} {queue.callbacks.length} · hot {queue.hot.length}
                          </span>
                        </div>
                        {queue.callbacks.slice(0, queueOpen ? undefined : 3).map((q) => queueRow(q, "callbacks"))}
                        {queue.hot.length > 0 && (
                          <div className="eyebrow" style={{ fontSize: 9.5, margin: "8px 10px 2px" }}>{t(myRole === "sales" ? "work.qPriority" : "work.qHot")}</div>
                        )}
                        {queue.hot.slice(0, queueOpen ? undefined : 3).map((q) => queueRow(q, "hot"))}
                        {queueOpen && queue.rest.length > 0 && (
                          <div className="eyebrow" style={{ fontSize: 9.5, margin: "8px 10px 2px" }}>{t("work.qRest")}</div>
                        )}
                        {queueOpen && queue.rest.map((q) => queueRow(q, "rest"))}
                        {queueOpen && queue.later.length > 0 && (
                          <div className="eyebrow" style={{ fontSize: 9.5, margin: "8px 10px 2px" }}>{t("work.qLater")}</div>
                        )}
                        {queueOpen && queue.later.map((q) => queueRow(q, "later"))}
                        <button
                          type="button"
                          onClick={() => setQueueOpen((v) => !v)}
                          style={{
                            display: "flex",
                            width: "100%",
                            padding: "7px 10px",
                            background: "none",
                            border: "none",
                            cursor: "pointer",
                            fontSize: 12.5,
                            fontWeight: 600,
                            color: "var(--text-dim)",
                          }}
                        >
                          {queueOpen
                            ? t("common.hide")
                            : t("work.queueMore", { n: Math.max(0, queue.rest.length + Math.max(0, queue.callbacks.length - 3) + Math.max(0, queue.hot.length - 3)), later: queue.later.length })}
                          <Icon name={queueOpen ? "chevronDown" : "chevronRight"} size={12} style={{ marginLeft: "auto" }} />
                        </button>
                      </>
                    )}
                  </Card>

                  {currentId && (
                    <Card padding={16} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 12 }}>
                      {!lead && <SkeletonLines lines={8} />}
                      {lead && (
                        <>
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <span style={{ fontSize: 18, fontWeight: 800 }}>{lead.name}</span>
                              {typeof lead.score_ai === "number" && (
                                <Chip tone={lead.score_ai >= 75 ? "positive" : "default"}>{Math.round(lead.score_ai)}</Chip>
                              )}
                              {phase === "during" && <Chip tone="problem">
                            <span className="m-live-on" style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "var(--cold)", marginRight: 6, verticalAlign: "middle" }} />
                            {fmtTimer(seconds)}
                          </Chip>}
                            </div>
                            <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>
                              {[lead.category, lead.address].filter(Boolean).join(" · ")}
                            </div>
                          </div>

                          {lead.advice && (
                            <div
                              style={{
                                padding: "11px 13px",
                                borderRadius: 10,
                                background: "var(--accent-soft)",
                                border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)",
                                fontSize: 13,
                                lineHeight: 1.55,
                              }}
                            >
                              <div className="eyebrow" style={{ marginBottom: 3, color: "var(--accent)", fontSize: 10 }}>
                                {t("work.whyCalling")}
                              </div>
                              {lead.advice}
                            </div>
                          )}

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            {factBox(t("lead.decisionMaker"), dm ? `${dm.name}${dm.title ? ` · ${dm.title}` : ""}` : "—")}
                            {factBox(
                              t("work.factLast"),
                              lead.last_touched_at
                                ? new Date(lead.last_touched_at).toLocaleDateString([], { day: "numeric", month: "short" })
                                : t("work.factNever"),
                            )}
                            {factBox(t("work.factReviews"), lead.rating != null ? `${lead.rating} · ${lead.reviews_count ?? 0}` : "—")}
                            {factBox(
                              t("work.factSite"),
                              [
                                lead.website ? t("common.yes") : t("common.no"),
                                lead.social_links && Object.keys(lead.social_links).length
                                  ? Object.keys(lead.social_links).map((k) => k.slice(0, 2).toUpperCase()).join(", ")
                                  : null,
                              ]
                                .filter(Boolean)
                                .join(" · "),
                            )}
                          </div>

                          <div className="seg" style={{ alignSelf: "flex-start" }}>
                            {(
                              [
                                ["summary", t("work.tabSummary")],
                                ["analysis", t("work.tabAnalysis")],
                                ["history", t("work.tabHistory")],
                                ["site", t("work.tabSite")],
                              ] as const
                            ).map(([key, label]) => (
                              <button key={key} type="button" className={tab === key ? "active" : ""} onClick={() => setTab(key)} style={{ padding: "4px 10px", fontSize: 12 }}>
                                {label}
                              </button>
                            ))}
                          </div>
                          <div style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--text-muted)", minHeight: 40, overflowY: "auto", maxHeight: 150 }}>
                            {tab === "summary" && (lead.summary || t("work.noData"))}
                            {tab === "analysis" && (
                              <div>
                                {(lead.strengths ?? []).map((x, i) => <div key={`s${i}`}>+ {x}</div>)}
                                {(lead.weaknesses ?? []).map((x, i) => <div key={`w${i}`} style={{ color: "var(--warm)" }}>− {x}</div>)}
                                {(lead.red_flags ?? []).map((x, i) => <div key={`r${i}`} style={{ color: "var(--cold)" }}>! {x}</div>)}
                                {!lead.strengths?.length && !lead.weaknesses?.length && t("work.noData")}
                              </div>
                            )}
                            {tab === "history" && <LeadCalls leadId={lead.id} showTitle={false} />}
                            {tab === "history" && <div style={{ marginTop: 6 }}>{lead.notes ? <>{t("lead.notes")}: {lead.notes}</> : null}</div>}
                            {tab === "site" && (
                              <div>
                                {lead.website ? (
                                  <a href={lead.website} target="_blank" rel="noreferrer">{lead.website}</a>
                                ) : (
                                  t("work.noSite")
                                )}
                                {lead.social_links &&
                                  Object.entries(lead.social_links).map(([k, v]) => (
                                    <div key={k}><a href={v} target="_blank" rel="noreferrer">{k}</a></div>
                                  ))}
                              </div>
                            )}
                          </div>

                          {funnel && (
                            <div style={{ marginTop: "auto", display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                              <span className="eyebrow" style={{ fontSize: 9.5, marginRight: 2 }}>{t("work.pathTitle")}</span>
                              {funnel.steps.map((s, i) => (
                                <Chip key={i} tone={i === currentStepIndex ? "accent" : "default"}>
                                  {i + 1} · {s.kind === "call" ? t("funnels.stepCall") : t("funnels.stepEmail")}
                                  {s.day_offset > 0 ? ` +${s.day_offset}д` : ""}
                                </Chip>
                              ))}
                            </div>
                          )}
                        </>
                      )}
                    </Card>
                  )}
                </div>

                {/* ── правая колонка: скрипт + управление ── */}
                {currentId && (
                  <div style={{ display: "grid", gridTemplateRows: "1fr auto", gap: 12, minWidth: 0, minHeight: 0 }}>
                    <Card padding={0} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", padding: "0 18px", borderBottom: "1px solid var(--border)" }}>
                        {(
                          [
                            ["script", t("work.scriptTab")],
                            ["objections", `${t("work.objectionsTitle")}${funnel?.objections?.length ? ` · ${funnel.objections.length}` : ""}`],
                            ["note", t("work.noteLabel")],
                          ] as const
                        ).map(([key, label]) => (
                          <button
                            key={key}
                            type="button"
                            onClick={() => setRightTab(key)}
                            style={{
                              background: "none",
                              border: "none",
                              borderBottom: "2px solid " + (rightTab === key ? "var(--accent)" : "transparent"),
                              padding: "12px 12px",
                              cursor: "pointer",
                              fontSize: 13,
                              fontWeight: 600,
                              color: rightTab === key ? "var(--text)" : "var(--text-dim)",
                            }}
                          >
                            {label}
                          </button>
                        ))}
                        {rightTab === "script" && (placeholders.contactName || placeholders.pain) && (
                          <span style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--text-dim)" }}>{t("work.scriptFilled")}</span>
                        )}
                        {funnel && (
                          <span style={{ marginLeft: rightTab === "script" ? 12 : "auto", fontSize: 11.5, color: "var(--text-dim)" }}>{funnel.name}</span>
                        )}
                      </div>

                      <div style={{ padding: "6px 22px 16px", overflowY: "auto", minHeight: 0, flex: 1 }}>
                        {rightTab === "script" &&
                          (sections.length === 0 ? (
                            <div style={{ fontSize: 13, color: "var(--text-dim)", padding: "14px 0" }}>{t("work.scriptEmpty")}</div>
                          ) : (
                            <div className="work-script">
                              {sections.map((sec, i) => {
                                const st = { nameUsed: false };
                                return (
                                  <div key={i} style={{ padding: "12px 0", borderBottom: "1px solid var(--border)", breakInside: "avoid" }}>
                                    {sec.title && (
                                      <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, fontWeight: 700 }}>
                                        <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--accent-soft)", color: "var(--accent)", display: "grid", placeItems: "center", fontSize: 11, fontWeight: 800, flexShrink: 0 }}>
                                          {i + 1}
                                        </span>
                                        {sec.title}
                                        {sec.hint && <span style={{ color: "var(--text-dim)", fontWeight: 600, fontSize: 12 }}>· {sec.hint}</span>}
                                      </div>
                                    )}
                                    <div style={{ margin: sec.title ? "8px 0 0 32px" : 0, fontSize: 13.5, lineHeight: 1.65 }}>
                                      {sec.lines.map((line, j) => (
                                        <div key={j}>
                                          {fillLine(line, placeholders, st).map((c, k) =>
                                            c.mark ? (
                                              <mark key={k} style={{ background: "var(--accent-soft)", color: "var(--accent)", padding: "0 4px", borderRadius: 4, fontWeight: 700 }}>
                                                {c.text}
                                              </mark>
                                            ) : (
                                              <span key={k}>{c.text}</span>
                                            ),
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ))}

                        {rightTab === "objections" &&
                          (funnel?.objections?.length ? (
                            <div className="work-script">
                              {funnel.objections.map((o, i) => (
                                <div key={i} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)", breakInside: "avoid" }}>
                                  <div style={{ fontSize: 13, fontWeight: 700 }}>«{o.objection}»</div>
                                  <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.55, marginTop: 3 }}>— {o.answer}</div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div style={{ fontSize: 13, color: "var(--text-dim)", padding: "14px 0" }}>{t("work.noData")}</div>
                          ))}

                        {rightTab === "note" && (
                          <div style={{ paddingTop: 12 }}>
                            <Textarea
                              ref={noteRef}
                              label={t("work.noteLabel")}
                              rows={10}
                              value={note}
                              onChange={(e) => setNote(e.target.value)}
                              placeholder={t("work.notePh")}
                            />
                          </div>
                        )}
                      </div>
                    </Card>

                    {/* Панель звонка */}
                    <Card padding={14} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      {celebrate && (
                        <span key={celebrate.at} className="m-success" role="status">
                          <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path pathLength={1} d="M4 10.5l4 4 8-9" />
                          </svg>
                          {celebrate.text}
                        </span>
                      )}
                      {lead && phase === "before" && (
                        <>
                          <Button key={lead.id} className={lead.phone ? "m-ring" : undefined} onClick={() => void startCall()} disabled={!lead.phone} style={{ padding: "11px 20px", fontSize: 14 }}>
                            <Icon name="phone" size={15} />
                            {t("work.callButton")}
                            {lead.phone ? ` · ${lead.phone}` : ""}
                          </Button>
                          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
                            {telephony?.enabled && telephony.mode === "browser"
                              ? t("work.recNoteBrowser")
                              : telephony?.enabled && telephony.my_extension
                                ? t("work.recNoteCallback")
                                : t("work.recNote")}
                          </span>
                          {nextLead && (
                            <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-dim)" }}>
                              {t("work.next")}: {nextLead.name}
                            </span>
                          )}
                        </>
                      )}
                      {lead && phase === "during" && (
                        <>
                          <Chip tone="problem">● {fmtTimer(seconds)}</Chip>
                          <span style={{ fontSize: 12.5, flex: 1, minWidth: 200 }}>
                            {recording ? (
                              <>
                                <b>{t("work.consentSay")}</b> «{consentPhrase(lead.phone)}»
                              </>
                            ) : (
                              t("work.recOffNote")
                            )}
                          </span>
                          {providerCallId && (
                            <button type="button" className={recording ? "btn btn-ghost btn-sm" : "btn btn-primary btn-sm"} onClick={() => void toggleRecording()}>
                              {recording ? t("work.recOff") : t("work.recOn")}
                            </button>
                          )}
                          {browserState && browserState !== "ended" && (
                            <>
                              <Chip>
                                {browserState === "active"
                                  ? t("work.browserActive")
                                  : browserState === "failed"
                                    ? t("work.browserFailed")
                                    : t("work.browserConnecting")}
                              </Chip>
                              {browserState === "active" && (
                                <Button variant="ghost" size="sm" onClick={toggleMute}>
                                  {muted ? t("work.unmute") : t("work.mute")}
                                </Button>
                              )}
                            </>
                          )}
                          <Button variant="ghost" size="sm" onClick={finishCall} style={{ color: "var(--cold)" }}>
                            {t("work.finishCall")}
                          </Button>
                        </>
                      )}
                      {lead && phase === "after" && !callbackPick && (
                        <>
                          <span className="eyebrow" style={{ fontSize: 10, marginRight: 4 }}>{t("work.outcome")}</span>
                          {outcomeBtn(funnel?.goal_name ?? t("work.oGoalFallback"), "G", () => applyOutcome("goal"), true)}
                          {outcomeBtn(t("work.oCallback"), "C", () => setCallbackPick(true))}
                          {outcomeBtn(t("work.oThinking"), "T", () => applyOutcome("thinking"))}
                          {outcomeBtn(t("work.oNoAnswer"), "N", () => applyOutcome("no_answer"))}
                          {outcomeBtn(t("work.oRefused"), "R", () => applyOutcome("refused"))}
                          {outcomeBtn(t("work.oWrongNumber"), "W", () => applyOutcome("wrong_number"))}
                          {nextLead && (
                            <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-dim)" }}>
                              {t("work.next")}: {nextLead.name}
                            </span>
                          )}
                        </>
                      )}
                      {lead && phase === "after" && callbackPick && (
                        <>
                          <span style={{ fontSize: 13 }}>{t("work.cbWhen")}</span>
                          {callbackChips.map((c) => (
                            <Button
                              key={c.hours}
                              variant="soft"
                              size="sm"
                              disabled={busy}
                              onClick={() => applyOutcome("callback", new Date(Date.now() + c.hours * 3600_000).toISOString())}
                            >
                              {c.label}
                            </Button>
                          ))}
                          <Button variant="ghost" size="sm" onClick={() => setCallbackPick(false)}>
                            {t("common.cancel")}
                          </Button>
                        </>
                      )}
                      {funnel && phase === "after" && (
                        <div style={{ width: "100%", fontSize: 11.5, color: "var(--text-dim)" }}>
                          {t("work.footnote", { n: funnel.no_answer_attempts, d: funnel.no_answer_pause_days })}
                        </div>
                      )}
                    </Card>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
