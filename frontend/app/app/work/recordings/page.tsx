"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/brand/Icon";
import { Card, EmptyState, Modal, SkeletonLines } from "@/components/ui";
import { RecordingPlayer } from "@/components/work/RecordingPlayer";
import { RubricView } from "@/components/work/RubricView";
import { TranscriptView } from "@/components/work/TranscriptView";
import { WorkModeSwitch } from "@/components/work/WorkModeSwitch";
import {
  analyzeCall,
  createCallReview,
  getArchiveCalls,
  getArchivePeople,
  getCallReview,
  listCallReviews,
  retryCallReview,
  type ArchiveCall,
  type ArchivePerson,
  type ArchiveResult,
  type CallReview,
} from "@/lib/api";
import { useActiveTeam } from "@/lib/hooks/useActiveTeam";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { showError } from "@/lib/toast";

const MAX_REVIEW = 30;
type Period = "today" | "7" | "30" | "custom";

const OUTCOME_KEYS: Record<string, TranslationKey> = {
  goal: "calls.outcome.goal",
  callback: "calls.outcome.callback",
  thinking: "calls.outcome.thinking",
  no_answer: "calls.outcome.no_answer",
  refused: "calls.outcome.refused",
  wrong_number: "calls.outcome.wrong_number",
};

const iso = (d: Date) => d.toISOString().slice(0, 10);
const mmss = (s: number | null) => {
  const v = Math.max(0, s ?? 0);
  return `${Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}`;
};
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Записи звонков по сотруднику и общий ИИ-разбор выбранных звонков.
 * Тимлид и выше: выбрал человека и период — видит все его звонки;
 * отметил нужные — получает разбор: повторяющиеся ошибки, возражения,
 * что делать. Разборы хранятся сессиями справа. */
export default function RecordingsPage() {
  const { t, lang } = useLocale();
  const { teamId, role } = useActiveTeam();
  const [people, setPeople] = useState<ArchivePerson[] | null>(null);
  const [userId, setUserId] = useState<number | null>(null);
  const [period, setPeriod] = useState<Period>("7");
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 6 * 86400000)));
  const [to, setTo] = useState(() => iso(new Date()));
  const [onlyTalks, setOnlyTalks] = useState(true);
  const [data, setData] = useState<ArchiveResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState("");
  const [reviews, setReviews] = useState<CallReview[] | null>(null);
  const [shown, setShown] = useState<CallReview | null>(null);
  const [starting, setStarting] = useState(false);

  const locale = lang === "en" ? "en-US" : lang === "uk" ? "uk-UA" : "ru-RU";

  useEffect(() => {
    if (!teamId || !role || role === "sales") return;
    getArchivePeople(teamId)
      .then((rows) => {
        setPeople(rows);
        setUserId((cur) => cur ?? (rows.find((p) => p.role === "sales" && p.calls > 0) ?? rows[0])?.user_id ?? null);
      })
      .catch((e) => showError(msg(e)));
  }, [teamId, role]);

  const range = useMemo(() => {
    const today = new Date();
    if (period === "today") return { from: iso(today), to: iso(today) };
    if (period === "7") return { from: iso(new Date(Date.now() - 6 * 86400000)), to: iso(today) };
    if (period === "30") return { from: iso(new Date(Date.now() - 29 * 86400000)), to: iso(today) };
    return { from, to };
  }, [period, from, to]);

  const loadCalls = useCallback(() => {
    if (!teamId || userId == null) return;
    setLoading(true);
    getArchiveCalls(teamId, { userId, dateFrom: range.from, dateTo: range.to, onlyTalks })
      .then((d) => {
        setData(d);
        setPicked(new Set());
      })
      .catch((e) => showError(msg(e)))
      .finally(() => setLoading(false));
  }, [teamId, userId, range.from, range.to, onlyTalks]);

  const loadReviews = useCallback(() => {
    if (!teamId) return;
    listCallReviews(teamId, userId ?? undefined).then(setReviews).catch(() => setReviews([]));
  }, [teamId, userId]);

  useEffect(loadCalls, [loadCalls]);
  useEffect(loadReviews, [loadReviews]);

  // Пока есть разбор «в работе» — подтягиваем историю раз в 4 секунды.
  useEffect(() => {
    if (!reviews?.some((r) => r.status === "running")) return;
    const h = window.setInterval(loadReviews, 4000);
    return () => window.clearInterval(h);
  }, [reviews, loadReviews]);

  // Звонки, отправленные на разбор кнопкой: список подтягивается, пока
  // у них не появится оценка (максимум ~3 минуты).
  const [pending, setPending] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (pending.size === 0) return;
    const started = Date.now();
    const h = window.setInterval(() => {
      if (!teamId || userId == null || Date.now() - started > 180000) {
        setPending(new Set());
        return;
      }
      getArchiveCalls(teamId, { userId, dateFrom: range.from, dateTo: range.to, onlyTalks })
        .then((d) => {
          setData(d);
          setPending((prev) => new Set([...prev].filter((id) => !d.calls.find((c) => c.id === id)?.analyzed)));
        })
        .catch(() => undefined);
    }, 6000);
    return () => window.clearInterval(h);
  }, [pending, teamId, userId, range.from, range.to, onlyTalks]);

  const analyzeOne = async (id: string) => {
    try {
      await analyzeCall(id);
      setPending((prev) => new Set(prev).add(id));
    } catch (e) {
      showError(msg(e));
    }
  };

  const reviewable = (data?.calls ?? []).filter((c) => c.has_transcript || c.has_recording);
  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < MAX_REVIEW) next.add(id);
      return next;
    });
  const pickAll = () => setPicked(new Set(reviewable.slice(0, MAX_REVIEW).map((c) => c.id)));

  const startReview = async () => {
    if (!teamId || picked.size === 0) return;
    setStarting(true);
    try {
      const r = await createCallReview(teamId, Array.from(picked), focus.trim() || undefined);
      setReviews((prev) => [r, ...(prev ?? [])]);
      setPicked(new Set());
      setFocus("");
    } catch (e) {
      showError(msg(e));
    } finally {
      setStarting(false);
    }
  };

  const retry = async (r: CallReview) => {
    try {
      const fresh = await retryCallReview(r.id);
      setReviews((prev) => (prev ?? []).map((x) => (x.id === r.id ? fresh : x)));
    } catch (e) {
      showError(msg(e));
    }
  };

  const openReview = async (r: CallReview) => {
    try {
      setShown(await getCallReview(r.id));
    } catch (e) {
      showError(msg(e));
    }
  };

  const person = people?.find((p) => p.user_id === userId);
  const callsById = useMemo(() => new Map((data?.calls ?? []).map((c) => [c.id, c])), [data]);

  if (role === "sales") {
    return (
      <>
        <Topbar crumbs={[{ label: t("nav.work"), href: "/app/work" }, { label: t("ca.tab") }]} right={<WorkModeSwitch mode="archive" />} />
        <div className="page"><Card><EmptyState icon={<Icon name="archive" size={20} />} title={t("ca.forLeads")} /></Card></div>
      </>
    );
  }

  return (
    <>
      <Topbar
        crumbs={[{ label: t("nav.work"), href: "/app/work" }, { label: t("ca.tab") }]}
        right={<WorkModeSwitch mode="archive" />}
      />
      <div className="page" style={{ display: "grid", gap: 14 }}>
        {/* ── фильтры ─────────────────────────────────────── */}
        <Card>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label style={{ display: "grid", gap: 4, minWidth: 220 }}>
              <span className="eyebrow">{t("ca.person")}</span>
              <select
                className="input"
                value={userId ?? ""}
                onChange={(e) => setUserId(Number(e.target.value))}
                disabled={!people}
              >
                {(people ?? []).map((p) => (
                  <option key={p.user_id} value={p.user_id}>
                    {p.name} · {t(`ca.role.${p.role}` as TranslationKey)} · {p.calls}
                  </option>
                ))}
              </select>
            </label>
            <div style={{ display: "grid", gap: 4 }}>
              <span className="eyebrow">{t("ca.period")}</span>
              <div className="seg" role="group" aria-label={t("ca.period")}>
                {(["today", "7", "30", "custom"] as Period[]).map((p) => (
                  <button key={p} type="button" className={period === p ? "active" : ""} onClick={() => setPeriod(p)}>
                    {t(`ca.p.${p}` as TranslationKey)}
                  </button>
                ))}
              </div>
            </div>
            {period === "custom" && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input className="input" type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} aria-label={t("ca.from")} style={{ height: 34 }} />
                <span style={{ color: "var(--text-dim)" }}>—</span>
                <input className="input" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} aria-label={t("ca.to")} style={{ height: 34 }} />
              </div>
            )}
            <button type="button" className="st-toggle-row" onClick={() => setOnlyTalks((v) => !v)} style={{ marginBottom: 6 }}>
              <span className={"st-switch" + (onlyTalks ? " on" : "")} />
              <span>{t("ca.onlyTalks")}</span>
            </button>
          </div>
          {data && (
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 14, fontSize: 13, color: "var(--text-muted)" }}>
              <span><b style={{ color: "var(--text)" }}>{data.stats.total}</b> {t("ca.s.calls")}</span>
              <span><b style={{ color: "var(--text)" }}>{data.stats.talks}</b> {t("ca.s.talks")}</span>
              <span><b style={{ color: "var(--text)" }}>{data.stats.talk_min}</b> {t("ca.s.min")}</span>
              {data.stats.avg_quality != null && (
                <span><b style={{ color: "var(--text)" }}>{data.stats.avg_quality}/10</b> {t("ca.s.quality")}</span>
              )}
            </div>
          )}
        </Card>

        <div className="ca-grid">
          {/* ── звонки ───────────────────────────────────── */}
          <Card padding={0}>
            <div className="ca-head">
              <div className="eyebrow">{person ? t("ca.callsOf", { name: person.name }) : t("ca.calls")}</div>
              {reviewable.length > 0 && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={picked.size ? () => setPicked(new Set()) : pickAll}>
                  {picked.size ? t("ca.unpick") : t("ca.pickAll", { n: Math.min(MAX_REVIEW, reviewable.length) })}
                </button>
              )}
            </div>
            {loading && !data && <div style={{ padding: 16 }}><SkeletonLines lines={5} /></div>}
            {data && data.calls.length === 0 && (
              <div style={{ padding: 16 }}><EmptyState icon={<Icon name="phone" size={20} />} title={t("ca.empty")} /></div>
            )}
            {data?.calls.map((c) => (
              <CallRow
                key={c.id}
                c={c}
                locale={locale}
                open={open === c.id}
                onOpen={() => setOpen((cur) => (cur === c.id ? null : c.id))}
                picked={picked.has(c.id)}
                onPick={() => toggle(c.id)}
                pickLimit={picked.size >= MAX_REVIEW}
                analyzing={pending.has(c.id)}
                onAnalyze={() => void analyzeOne(c.id)}
              />
            ))}
            {picked.size > 0 && (
              <div className="ca-bar">
                <b>{t("ca.picked", { n: picked.size, max: MAX_REVIEW })}</b>
                <input
                  className="input"
                  value={focus}
                  onChange={(e) => setFocus(e.target.value)}
                  placeholder={t("ca.focusPh")}
                  maxLength={500}
                  style={{ flex: "1 1 220px", height: 34 }}
                />
                <button type="button" className="btn" disabled={starting} onClick={() => void startReview()}>
                  <Icon name="sparkles" size={13} /> {starting ? t("common.loading") : t("ca.analyze")}
                </button>
              </div>
            )}
          </Card>

          {/* ── разборы ──────────────────────────────────── */}
          <Card>
            <div className="eyebrow" style={{ marginBottom: 4 }}>{t("ca.reviews")}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-dim)", marginBottom: 10 }}>{t("ca.reviewsHint")}</div>
            {!reviews && <SkeletonLines lines={3} />}
            {reviews?.length === 0 && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("ca.noReviews")}</div>}
            {reviews?.map((r, i) => (
              <div key={r.id} className={"ca-review" + (i === 0 ? " first" : "")}>
                <button
                  type="button"
                  className="ca-review-open"
                  onClick={() => r.status === "done" && void openReview(r)}
                  disabled={r.status !== "done"}
                >
                  <span className={"ca-pill " + r.status}>{t(`ca.st.${r.status}` as TranslationKey)}</span>
                  <span style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
                    <span style={{ display: "block", fontWeight: 600, color: "var(--text)" }}>
                      {r.subject ?? t("ca.several")} · {t("ca.nCalls", { n: r.calls })}
                    </span>
                    <span className="ca-review-meta">
                      {r.created_at ? new Date(r.created_at).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}
                      {r.created_by ? ` · ${r.created_by}` : ""}
                      {r.focus ? ` · «${r.focus}»` : ""}
                    </span>
                  </span>
                  {r.status === "done" && <Icon name="chevronRight" size={13} style={{ color: "var(--text-dim)" }} />}
                </button>
                {r.status === "failed" && (
                  <div className="ca-review-fail">
                    <span>{t("ca.failedWhy")}</span>
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => void retry(r)}>
                      <Icon name="rotateCcw" size={12} /> {t("ca.retry")}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </Card>
        </div>
      </div>

      {shown && (
        <Modal open onClose={() => setShown(null)} title={t("ca.reviewTitle", { n: shown.calls })} width={680}>
          <ReviewView review={shown} callsById={callsById} locale={locale} />
        </Modal>
      )}
    </>
  );
}

function CallRow({
  c,
  locale,
  open,
  onOpen,
  picked,
  onPick,
  pickLimit,
  analyzing,
  onAnalyze,
}: {
  c: ArchiveCall;
  locale: string;
  open: boolean;
  onOpen: () => void;
  picked: boolean;
  onPick: () => void;
  pickLimit: boolean;
  analyzing: boolean;
  onAnalyze: () => void;
}) {
  const { t } = useLocale();
  const [showText, setShowText] = useState(false);
  const outcome = c.outcome && OUTCOME_KEYS[c.outcome] ? t(OUTCOME_KEYS[c.outcome]) : null;
  return (
    <div className={"ca-row" + (open ? " open" : "")}>
      <div className="ca-line">
        <input
          type="checkbox"
          checked={picked}
          onChange={onPick}
          disabled={!(c.has_transcript || c.has_recording) || (!picked && pickLimit)}
          title={c.has_transcript || c.has_recording ? undefined : t("ca.noTranscript")}
          aria-label={t("ca.pick")}
        />
        <button type="button" className="ca-main" onClick={onOpen} aria-expanded={open}>
          <Icon name={open ? "chevronDown" : "chevronRight"} size={13} style={{ color: "var(--text-dim)", flexShrink: 0 }} />
          <span className="ca-when">
            {c.created_at ? new Date(c.created_at).toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}
          </span>
          <span className="ca-who">{c.lead_name ?? c.to_number ?? "—"}</span>
          <span className="ca-dur">{mmss(c.talk_sec)}</span>
          {outcome && <span className="chip" style={{ fontSize: 11 }}>{outcome}</span>}
          {typeof c.quality_score === "number" && <span className="chip" style={{ fontSize: 11 }}>{c.quality_score}/10</span>}
          {c.has_recording && <Icon name="phone" size={12} style={{ color: "var(--text-dim)" }} />}
        </button>
      </div>
      {open && (
        <div className="ca-body">
          {c.has_recording ? <RecordingPlayer callId={c.id} /> : <div className="ca-dim">{t("ca.noRecording")}</div>}
          {c.summary && <div>{c.summary}</div>}
          {c.objections.length > 0 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {c.objections.map((o) => (
                <span key={o} className="chip" style={{ fontSize: 11, color: "var(--warm)", borderColor: "var(--warm)" }}>{o}</span>
              ))}
            </div>
          )}
          {c.quality_notes && <div className="ca-dim">{c.quality_notes}</div>}
          {c.too_short && <div className="ca-dim">{t("ca.tooShort")}</div>}
          {c.rubric.length > 0 && <RubricView items={c.rubric} />}
          {c.has_recording && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ justifySelf: "start" }}
              disabled={analyzing}
              onClick={onAnalyze}
            >
              <Icon name="sparkles" size={12} />
              {analyzing ? t("ca.analyzing") : c.analyzed ? t("ca.reanalyze") : t("ca.analyzeOne")}
            </button>
          )}
          {c.transcript && c.transcript.length > 0 && (
            <>
              <button type="button" className="btn btn-ghost btn-sm" style={{ justifySelf: "start" }} onClick={() => setShowText((v) => !v)}>
                {showText ? t("ca.hideText") : t("ca.showText")}
              </button>
              {showText && <TranscriptView segments={c.transcript} />}
            </>
          )}
          {c.lead_id && (
            <Link href={`/app/leads/${c.lead_id}`} style={{ fontSize: 12.5, color: "var(--accent)" }}>{t("ca.openLead")}</Link>
          )}
        </div>
      )}
    </div>
  );
}

function ReviewView({
  review,
  callsById,
  locale,
}: {
  review: CallReview;
  callsById: Map<string, ArchiveCall>;
  locale: string;
}) {
  const { t } = useLocale();
  const r = review.result ?? {};
  const map = r.call_map ?? {};
  const callLabel = (n: number) => {
    const c = callsById.get(map[String(n)] ?? "");
    const when = c?.created_at ? new Date(c.created_at).toLocaleDateString(locale, { day: "numeric", month: "short" }) : "";
    return `№${n}${c?.lead_name ? ` · ${c.lead_name}` : ""}${when ? ` · ${when}` : ""}`;
  };
  const verdictTone = r.verdict === "strong" ? "var(--accent)" : r.verdict === "weak" ? "var(--cold)" : "var(--warm)";
  return (
    <div style={{ display: "grid", gap: 16, fontSize: 13.5, lineHeight: 1.55 }}>
      {r.truncated && <div className="ca-dim">{t("ca.truncated")}</div>}
      <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
        {typeof r.score === "number" && (
          <div style={{ fontSize: 28, fontWeight: 800, color: verdictTone, fontVariantNumeric: "tabular-nums" }}>{r.score}<span style={{ fontSize: 14, color: "var(--text-dim)" }}>/10</span></div>
        )}
        <div style={{ color: "var(--text)" }}>{r.summary}</div>
      </div>
      {review.subject && (
        <div className="ca-dim">{review.subject} · {review.focus ? `«${review.focus}» · ` : ""}{review.created_by ?? ""}</div>
      )}

      {(r.mistakes ?? []).length > 0 && (
        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("ca.r.mistakes")}</div>
          {(r.mistakes ?? []).map((m, i) => (
            <div key={i} className="ca-item">
              <div style={{ fontWeight: 700 }}>{m.title}</div>
              {m.example && <div className="ca-quote">«{m.example}»</div>}
              {m.fix && <div><span className="ca-dim">{t("ca.r.fix")}:</span> {m.fix}</div>}
              {m.calls?.length ? <div className="ca-dim">{m.calls.map(callLabel).join(" · ")}</div> : null}
            </div>
          ))}
        </section>
      )}

      {(r.objections ?? []).length > 0 && (
        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("ca.r.objections")}</div>
          {(r.objections ?? []).map((o, i) => (
            <div key={i} className="ca-item">
              <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                <b>{o.text}</b>
                {o.calls?.length ? <span className="ca-dim">{t("ca.r.times", { n: o.calls.length })}</span> : null}
                {o.handled && <span className={"ca-pill " + (o.handled === "well" ? "done" : o.handled === "badly" ? "failed" : "running")}>{t(`ca.r.h.${o.handled}` as TranslationKey)}</span>}
              </div>
              {o.better_answer && <div><span className="ca-dim">{t("ca.r.better")}:</span> {o.better_answer}</div>}
            </div>
          ))}
        </section>
      )}

      {(r.strengths ?? []).length > 0 && (
        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("ca.r.strengths")}</div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>{(r.strengths ?? []).map((s, i) => <li key={i}>{s}</li>)}</ul>
        </section>
      )}

      {(r.recommendations ?? []).length > 0 && (
        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("ca.r.next")}</div>
          <ol style={{ margin: 0, paddingLeft: 18 }}>{(r.recommendations ?? []).map((s, i) => <li key={i}>{s}</li>)}</ol>
        </section>
      )}

      {(r.per_call ?? []).length > 0 && (
        <section>
          <div className="eyebrow" style={{ marginBottom: 6 }}>{t("ca.r.perCall")}</div>
          {(r.per_call ?? []).map((p) => (
            <div key={p.n} className="st-row" style={{ justifyContent: "flex-start", gap: 10 }}>
              <span style={{ minWidth: 0, flex: 1 }}>{callLabel(p.n)}{p.note ? ` — ${p.note}` : ""}</span>
              {typeof p.score === "number" && <span style={{ fontWeight: 700 }}>{p.score}/10</span>}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
