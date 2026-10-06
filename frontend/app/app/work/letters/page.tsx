"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/brand/Icon";
import { Card, Chip, SkeletonLines } from "@/components/ui";
import { LeadCalls } from "@/components/leads/LeadCalls";
import { WorkModeSwitch } from "@/components/work/WorkModeSwitch";
import {
  checkSpamScore,
  draftLeadEmail,
  getClassifiedReplies,
  getInboxThread,
  getInboxThreads,
  getLead,
  getWorkLetters,
  replyInThread,
  sendLeadEmail,
  type ClassifiedReply,
  type EmailDraftLanguage,
  type EmailTone,
  type InboxThreadDetail,
  type InboxThreadSummary,
  type Lead,
  type LetterRow,
  type SpamCheckResult,
  type WorkLetters,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { showError, showSuccess } from "@/lib/toast";

type Filter = "all" | "replied" | "pending" | "scheduled";
type Sel =
  | { kind: "thread"; thread: InboxThreadSummary }
  | { kind: "letter"; row: LetterRow; scheduled: boolean }
  | null;

const CAT_KEY: Record<string, TranslationKey> = {
  interested: "inbox.cat.interested",
  meeting_request: "inbox.cat.meeting",
  question: "inbox.cat.question",
  objection: "inbox.cat.objection",
  not_interested: "inbox.cat.notInterested",
  unsubscribe: "inbox.cat.unsubscribe",
};
const CAT_TONE: Record<string, "positive" | "accent" | "problem" | "default"> = {
  interested: "positive",
  meeting_request: "positive",
  question: "accent",
  objection: "problem",
  not_interested: "default",
  unsubscribe: "default",
};

function toMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Письма — вторая половина работы селза. Слева всё, что требует
 * внимания: ответы (уже разобраны ИИ), письма воронки на одобрение,
 * автоматические; в центре диалог и черновик ответа от Henry; справа
 * лид и инструменты ИИ. Прозвон — соседняя страница, переключатель в
 * шапке. */
export default function LettersPage() {
  const { t, lang } = useLocale();
  const [teamId, setTeamId] = useState<string | undefined>(() => activeTeamId());
  useEffect(() => subscribeWorkspace(() => setTeamId(activeTeamId())), []);

  const [letters, setLetters] = useState<WorkLetters | null>(null);
  const [threads, setThreads] = useState<InboxThreadSummary[] | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [replies, setReplies] = useState<Record<string, ClassifiedReply>>({});
  const [filter, setFilter] = useState<Filter>("all");
  const [sel, setSel] = useState<Sel>(null);

  const reload = useCallback(() => {
    if (!teamId) return;
    getWorkLetters(teamId).then(setLetters).catch((e) => showError(toMessage(e)));
    getInboxThreads({ limit: 60 })
      .then((r) => {
        setConnected(r.connected && !r.needs_reconnect);
        setThreads(r.threads);
      })
      .catch(() => {
        setConnected(false);
        setThreads([]);
      });
    getClassifiedReplies(teamId)
      .then((r) => {
        const map: Record<string, ClassifiedReply> = {};
        for (const x of r.replies) if (!map[x.lead_id]) map[x.lead_id] = x;
        setReplies(map);
      })
      .catch(() => undefined);
  }, [teamId]);

  useEffect(() => {
    setSel(null);
    reload();
  }, [reload]);

  const repliedThreads = useMemo(
    () => (threads ?? []).filter((th) => th.lead_id && replies[th.lead_id]),
    [threads, replies],
  );
  const otherThreads = useMemo(
    () => (threads ?? []).filter((th) => !(th.lead_id && replies[th.lead_id])),
    [threads, replies],
  );

  // Первый пункт списка выбираем сами, чтобы страница не открывалась пустой.
  useEffect(() => {
    if (sel || !threads || !letters) return;
    if (repliedThreads[0]) setSel({ kind: "thread", thread: repliedThreads[0] });
    else if (letters.pending_approval[0]) setSel({ kind: "letter", row: letters.pending_approval[0], scheduled: false });
    else if (threads[0]) setSel({ kind: "thread", thread: threads[0] });
  }, [sel, threads, letters, repliedThreads]);

  const selLeadId = sel?.kind === "thread" ? sel.thread.lead_id : sel?.kind === "letter" ? sel.row.lead_id : null;
  const isSel = (x: Sel) =>
    !!sel &&
    !!x &&
    sel.kind === x.kind &&
    (sel.kind === "thread" && x.kind === "thread"
      ? sel.thread.thread_id === x.thread.thread_id
      : sel.kind === "letter" && x.kind === "letter"
        ? sel.row.lead_id === x.row.lead_id
        : false);

  const when = (iso: string | null) => {
    if (!iso) return "";
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    if (diff < 3_600_000) return t("inbox.relative.m", { n: Math.max(1, Math.floor(diff / 60_000)) });
    if (diff < 86_400_000) return t("inbox.relative.h", { n: Math.floor(diff / 3_600_000) });
    return d.toLocaleDateString([], { day: "numeric", month: "short" });
  };

  const row = (
    key: string,
    title: string,
    sub: string | null,
    right: React.ReactNode,
    active: boolean,
    onClick: () => void,
    unread?: boolean,
    cat?: string | null,
  ) => (
    <button
      key={key}
      type="button"
      onClick={onClick}
      style={{
        display: "grid",
        gap: 3,
        width: "100%",
        padding: "8px 10px",
        borderRadius: 9,
        border: "1px solid " + (active ? "var(--accent)" : "transparent"),
        background: active ? "var(--accent-soft)" : "transparent",
        cursor: "pointer",
        textAlign: "left",
        color: "var(--text)",
      }}
    >
      <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700 }}>
        {unread && <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }} />}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
        {cat && CAT_KEY[cat] && (
          <Chip tone={CAT_TONE[cat] ?? "default"}>
            <span style={{ fontSize: 10.5 }}>{t(CAT_KEY[cat])}</span>
          </Chip>
        )}
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)", fontWeight: 600, flexShrink: 0 }}>{right}</span>
      </span>
      {sub && (
        <span style={{ fontSize: 12, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</span>
      )}
    </button>
  );

  const sep = (text: string) => (
    <div className="eyebrow" style={{ fontSize: 9.5, margin: "10px 10px 3px" }}>{text}</div>
  );

  const counts = {
    replied: repliedThreads.length,
    pending: letters?.pending_approval.length ?? 0,
    scheduled: letters?.scheduled.length ?? 0,
  };
  const hotReplies = Object.values(replies).filter((r) => r.category === "interested" || r.category === "meeting_request").length;

  return (
    <>
      <Topbar crumbs={[{ label: t("letters.tabLetters") }]} right={<WorkModeSwitch mode="letters" />} />
      <div className="page" style={{ maxWidth: 1500, display: "flex", flexDirection: "column", gap: 12 }}>
        {/* Счёт дня */}
        <div style={{ display: "flex", alignItems: "center", gap: 22, flexWrap: "wrap" }}>
          {letters &&
            (
              [
                [t("lt.sent"), `${letters.sent_today}/${letters.cap}`, t("lt.warmup", { day: letters.warmup_day })],
                [t("lt.replies"), counts.replied, null],
                [t("lt.hot"), hotReplies, null],
              ] as const
            ).map(([label, value, hint]) => (
              <div key={label} style={{ display: "flex", gap: 7, alignItems: "baseline" }}>
                <span style={{ fontSize: 9.5, fontWeight: 800, letterSpacing: "0.09em", textTransform: "uppercase", color: "var(--text-dim)" }}>{label}</span>
                <span style={{ fontSize: 16, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{value}</span>
                {hint && <span style={{ fontSize: 11.5, color: "var(--text-dim)" }}>· {hint}</span>}
              </div>
            ))}
          <span style={{ marginLeft: "auto" }}>
            {connected === false ? (
              <Link href="/app/settings" className="btn btn-primary btn-sm">
                {t("inbox.connect.action")}
              </Link>
            ) : connected ? (
              <span className="chip" style={{ fontSize: 11.5 }}>
                <Icon name="check" size={11} /> {t("lt.mailConnected")}
              </span>
            ) : null}
          </span>
        </div>

        <div className="letters-grid">
          {/* ── список ── */}
          <Card padding={12} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 4 }}>
              {(
                [
                  ["all", `${t("inbox.cat.all")} · ${counts.replied + counts.pending + counts.scheduled + otherThreads.length}`],
                  ["replied", `${t("lt.replied")} · ${counts.replied}`],
                  ["pending", `${t("lt.pending")} · ${counts.pending}`],
                  ["scheduled", `${t("lt.scheduled")} · ${counts.scheduled}`],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setFilter(k)}
                  className="chip"
                  style={{
                    cursor: "pointer",
                    fontSize: 11.5,
                    ...(filter === k ? { background: "var(--accent-soft)", color: "var(--accent)", borderColor: "var(--accent)" } : {}),
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <div style={{ overflowY: "auto", minHeight: 0, flex: 1 }}>
              {threads === null && <SkeletonLines lines={6} />}
              {threads !== null && (filter === "all" || filter === "replied") && repliedThreads.length > 0 && (
                <>
                  {sep(t("lt.sepReplied"))}
                  {repliedThreads.map((th) => {
                    const r = replies[th.lead_id!];
                    return row(
                      th.thread_id,
                      th.lead_name ?? th.counterpart_email ?? t("inbox.unknownSender"),
                      th.snippet,
                      when(th.last_message_at),
                      isSel({ kind: "thread", thread: th }),
                      () => setSel({ kind: "thread", thread: th }),
                      th.unread_count > 0,
                      r?.category,
                    );
                  })}
                </>
              )}
              {letters && (filter === "all" || filter === "pending") && letters.pending_approval.length > 0 && (
                <>
                  {sep(t("lt.sepPending"))}
                  {letters.pending_approval.map((lr) =>
                    row(
                      `p-${lr.lead_id}`,
                      lr.lead_name,
                      lr.note,
                      t("letters.touch", { i: lr.step_index, n: lr.steps_total }),
                      isSel({ kind: "letter", row: lr, scheduled: false }),
                      () => setSel({ kind: "letter", row: lr, scheduled: false }),
                    ),
                  )}
                </>
              )}
              {letters && (filter === "all" || filter === "scheduled") && letters.scheduled.length > 0 && (
                <>
                  {sep(t("lt.sepScheduled"))}
                  {letters.scheduled.map((lr) =>
                    row(
                      `s-${lr.lead_id}`,
                      lr.lead_name,
                      lr.note,
                      lr.due_at ? new Date(lr.due_at).toLocaleDateString([], { day: "numeric", month: "short" }) : "",
                      isSel({ kind: "letter", row: lr, scheduled: true }),
                      () => setSel({ kind: "letter", row: lr, scheduled: true }),
                    ),
                  )}
                </>
              )}
              {threads !== null && filter === "all" && otherThreads.length > 0 && (
                <>
                  {sep(t("lt.sepOther"))}
                  {otherThreads.map((th) =>
                    row(
                      th.thread_id,
                      th.lead_name ?? th.counterpart_email ?? t("inbox.unknownSender"),
                      th.snippet,
                      when(th.last_message_at),
                      isSel({ kind: "thread", thread: th }),
                      () => setSel({ kind: "thread", thread: th }),
                      th.unread_count > 0,
                    ),
                  )}
                </>
              )}
              {threads !== null && letters && threads.length === 0 && counts.pending + counts.scheduled === 0 && (
                <div style={{ fontSize: 12.5, color: "var(--text-dim)", padding: 10 }}>{t("inbox.empty.threads")}</div>
              )}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-dim)", paddingTop: 8 }}>{t("letters.suppressionNote")}</div>
          </Card>

          {/* ── диалог / письмо ── */}
          {sel?.kind === "thread" && (
            <ThreadPane key={sel.thread.thread_id} summary={sel.thread} reply={sel.thread.lead_id ? replies[sel.thread.lead_id] : undefined} lang={lang} onSent={reload} />
          )}
          {sel?.kind === "letter" && <LetterPane key={sel.row.lead_id} row={sel.row} scheduled={sel.scheduled} lang={lang} onSent={reload} />}
          {!sel && <Card style={{ display: "grid", placeItems: "center", color: "var(--text-dim)", fontSize: 13 }}>{t("inbox.detail.emptyTitle")}</Card>}

          {/* ── лид + инструменты ── */}
          <LeadPane leadId={selLeadId ?? null} />
        </div>
      </div>
    </>
  );
}

/* ── центр: переписка ─────────────────────────────────────────────── */

function useComposer(leadId: string | null, lang: string, initial: string, initialSubject: string | null) {
  const [tone, setTone] = useState<EmailTone>("professional");
  const [emailLang, setEmailLang] = useState<EmailDraftLanguage>((["ru", "uk", "en"].includes(lang) ? lang : "ru") as EmailDraftLanguage);
  const [body, setBody] = useState(initial);
  const [subject, setSubject] = useState(initialSubject ?? "");
  const [drafting, setDrafting] = useState(false);
  const [spam, setSpam] = useState<SpamCheckResult | null>(null);

  const rewrite = async (extra?: string) => {
    if (!leadId) return;
    setDrafting(true);
    try {
      const d = await draftLeadEmail(leadId, { tone, language: emailLang, extraContext: extra });
      setBody(d.body);
      if (!initialSubject) setSubject(d.subject);
      setSpam(null);
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setDrafting(false);
    }
  };
  const check = async () => {
    try {
      setSpam(await checkSpamScore(subject || null, body));
    } catch (e) {
      showError(toMessage(e));
    }
  };
  return { tone, setTone, emailLang, setEmailLang, body, setBody, subject, setSubject, drafting, rewrite, spam, check, setSpam };
}

function ComposerBar(p: ReturnType<typeof useComposer> & { title: string; extraHint?: string }) {
  const { t } = useLocale();
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <span className="eyebrow" style={{ fontSize: 10, marginRight: 4 }}>{p.title}</span>
      {(
        [
          ["professional", t("lt.toneBiz")],
          ["casual", t("lt.toneSimple")],
          ["bold", t("lt.toneBold")],
        ] as const
      ).map(([k, label]) => (
        <button key={k} type="button" className="chip" onClick={() => p.setTone(k)} style={{ cursor: "pointer", fontSize: 11.5, ...(p.tone === k ? { background: "var(--accent-soft)", color: "var(--accent)", borderColor: "var(--accent)" } : {}) }}>
          {label}
        </button>
      ))}
      {(["uk", "ru", "en"] as EmailDraftLanguage[]).map((l) => (
        <button key={l} type="button" className="chip" onClick={() => p.setEmailLang(l)} style={{ cursor: "pointer", fontSize: 11.5, ...(p.emailLang === l ? { background: "var(--accent-soft)", color: "var(--accent)", borderColor: "var(--accent)" } : {}) }}>
          {l.toUpperCase()}
        </button>
      ))}
      <button type="button" className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} disabled={p.drafting} onClick={() => void p.rewrite(p.extraHint)}>
        <Icon name="sparkles" size={12} /> {p.drafting ? t("common.loading") : t("lt.rewrite")}
      </button>
    </div>
  );
}

function SpamChip({ spam, onCheck }: { spam: SpamCheckResult | null; onCheck: () => void }) {
  const { t } = useLocale();
  if (!spam)
    return (
      <button type="button" className="chip" onClick={onCheck} style={{ cursor: "pointer", fontSize: 11.5 }}>
        {t("lt.spamCheck")}
      </button>
    );
  const tone = spam.verdict === "ok" ? "positive" : spam.verdict === "risky" ? "accent" : "problem";
  return (
    <Chip tone={tone}>
      <span style={{ fontSize: 11 }} title={spam.issues.join("\n")}>
        {t("lt.spam")}: {spam.verdict === "ok" ? t("lt.spamOk") : spam.verdict === "risky" ? t("lt.spamRisky") : t("lt.spamBad")}
      </span>
    </Chip>
  );
}

function ThreadPane({
  summary,
  reply,
  lang,
  onSent,
}: {
  summary: InboxThreadSummary;
  reply?: ClassifiedReply;
  lang: string;
  onSent: () => void;
}) {
  const { t } = useLocale();
  const [detail, setDetail] = useState<InboxThreadDetail | null>(null);
  const [sending, setSending] = useState(false);
  const c = useComposer(summary.lead_id, lang, reply?.suggested_reply ?? "", summary.subject ? `Re: ${summary.subject.replace(/^re:\s*/i, "")}` : null);

  useEffect(() => {
    let cancelled = false;
    getInboxThread(summary.thread_id)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => showError(toMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [summary.thread_id]);

  const send = async () => {
    if (!c.body.trim()) return;
    setSending(true);
    try {
      await replyInThread(summary.thread_id, c.body, c.subject || null);
      showSuccess(t("inbox.reply.sent"));
      c.setBody("");
      onSent();
      const d = await getInboxThread(summary.thread_id);
      setDetail(d);
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <Card padding={0} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 800 }}>{summary.lead_name ?? summary.counterpart_email ?? t("inbox.unknownSender")}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {summary.subject ?? t("inbox.noSubject")} · {summary.counterpart_email}
          </div>
        </div>
        {summary.lead_id && (
          <>
            <Link href={`/app/work?lead=${summary.lead_id}`} className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }}>
              <Icon name="phone" size={12} /> {t("lt.toCalls")}
            </Link>
            <Link href={`/app/leads?lead=${summary.lead_id}`} className="btn btn-ghost btn-sm">
              {t("inbox.viewLead")}
            </Link>
          </>
        )}
      </div>

      <div style={{ padding: "14px 18px", display: "flex", flexDirection: "column", gap: 10, overflowY: "auto", minHeight: 0, flex: 1 }}>
        {!detail && <SkeletonLines lines={4} />}
        {detail?.messages.map((m) => (
          <div
            key={m.id}
            style={{
              alignSelf: m.direction === "outbound" ? "flex-end" : "flex-start",
              maxWidth: "80%",
              padding: "10px 13px",
              borderRadius: 12,
              background: m.direction === "outbound" ? "var(--accent-soft)" : "var(--surface-2)",
              border: m.direction === "outbound" ? "1px solid color-mix(in srgb, var(--accent) 20%, transparent)" : "1px solid transparent",
              fontSize: 13,
              lineHeight: 1.55,
              whiteSpace: "pre-wrap",
            }}
          >
            <div style={{ fontSize: 11, color: "var(--text-dim)", fontWeight: 600, marginBottom: 3 }}>
              {m.direction === "outbound" ? t("lt.you") : m.from_email} · {m.sent_at ? new Date(m.sent_at).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : ""}
            </div>
            {m.body_text || t("inbox.message.htmlOnly")}
          </div>
        ))}
        {reply && (
          <div style={{ padding: "11px 13px", borderRadius: 10, background: "var(--accent-soft)", border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)", fontSize: 12.5, lineHeight: 1.5 }}>
            <div className="eyebrow" style={{ fontSize: 10, color: "var(--accent)", marginBottom: 3 }}>
              {t("inbox.aiVerdict")} · {CAT_KEY[reply.category] ? t(CAT_KEY[reply.category]) : reply.category}
              {reply.sentiment ? ` · ${reply.sentiment}` : ""}
            </div>
            {reply.summary ?? reply.preview}
          </div>
        )}
      </div>

      <div style={{ padding: "12px 18px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 8 }}>
        <ComposerBar {...c} title={t("lt.draftTitle")} extraHint={reply ? `${t("lt.replyTo")}: ${reply.preview}` : undefined} />
        <textarea
          className="textarea"
          rows={4}
          value={c.body}
          onChange={(e) => {
            c.setBody(e.target.value);
            c.setSpam(null);
          }}
          placeholder={t("inbox.reply.placeholder")}
          style={{ fontSize: 13 }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-sm" disabled={sending || !c.body.trim()} onClick={() => void send()}>
            {sending ? t("inbox.reply.sending") : t("inbox.reply.send")}
          </button>
          <SpamChip spam={c.spam} onCheck={() => void c.check()} />
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{t("inbox.sendHint")}</span>
        </div>
      </div>
    </Card>
  );
}

/* ── центр: письмо воронки ───────────────────────────────────────── */

function LetterPane({ row, scheduled, lang, onSent }: { row: LetterRow; scheduled: boolean; lang: string; onSent: () => void }) {
  const { t } = useLocale();
  const [lead, setLead] = useState<Lead | null>(null);
  const [sending, setSending] = useState(false);
  const c = useComposer(row.lead_id, lang, "", null);

  useEffect(() => {
    let cancelled = false;
    getLead(row.lead_id)
      .then((l) => !cancelled && setLead(l))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [row.lead_id]);

  const to = lead?.contact_email ?? lead?.website_meta?.emails?.[0] ?? lead?.website_meta?.contact_person?.email ?? null;

  const send = async () => {
    if (!c.body.trim() || !c.subject.trim()) return;
    setSending(true);
    try {
      await sendLeadEmail({ leadId: row.lead_id, subject: c.subject, body: c.body, to: to ?? undefined });
      showSuccess(t("inbox.reply.sent"));
      onSent();
    } catch (e) {
      showError(toMessage(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <Card padding={0} style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ padding: "12px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 800 }}>{row.lead_name}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            {row.funnel_name ?? ""} · {t("letters.touch", { i: row.step_index, n: row.steps_total })}
            {scheduled && row.due_at ? ` · ${t("lt.dueAt", { d: new Date(row.due_at).toLocaleDateString([], { day: "numeric", month: "short" }) })}` : ""}
          </div>
        </div>
        <Link href={`/app/work?lead=${row.lead_id}`} className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }}>
          <Icon name="phone" size={12} /> {t("lt.toCalls")}
        </Link>
      </div>
      <div style={{ padding: "14px 18px", display: "grid", gap: 10, overflowY: "auto", minHeight: 0, flex: 1, alignContent: "start" }}>
        {row.note && (
          <div style={{ padding: "11px 13px", borderRadius: 10, background: "var(--accent-soft)", border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)", fontSize: 12.5, lineHeight: 1.5 }}>
            <div className="eyebrow" style={{ fontSize: 10, color: "var(--accent)", marginBottom: 3 }}>{t("lt.touchNote")}</div>
            {row.note}
          </div>
        )}
        {scheduled && <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{t("letters.workerNote")}</div>}
        {!c.body && !c.drafting && (
          <button type="button" className="btn btn-sm" style={{ justifySelf: "start" }} onClick={() => void c.rewrite(row.note ?? undefined)}>
            <Icon name="sparkles" size={12} /> {t("lt.draftForTouch")}
          </button>
        )}
        {c.drafting && <SkeletonLines lines={4} />}
      </div>
      <div style={{ padding: "12px 18px 14px", borderTop: "1px solid var(--border)", display: "grid", gap: 8 }}>
        <ComposerBar {...c} title={t("lt.letterTitle")} extraHint={row.note ?? undefined} />
        <input className="input" value={c.subject} onChange={(e) => c.setSubject(e.target.value)} placeholder={t("lt.subjectPh")} style={{ fontSize: 13 }} />
        <textarea className="textarea" rows={5} value={c.body} onChange={(e) => { c.setBody(e.target.value); c.setSpam(null); }} placeholder={t("lt.bodyPh")} style={{ fontSize: 13 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-sm" disabled={sending || !c.body.trim() || !c.subject.trim() || !to} onClick={() => void send()}>
            {sending ? t("inbox.reply.sending") : t("inbox.reply.send")}
          </button>
          <SpamChip spam={c.spam} onCheck={() => void c.check()} />
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{to ? t("lt.sendTo", { to }) : t("lead.email.noAddress")}</span>
        </div>
      </div>
    </Card>
  );
}

/* ── справа: лид и инструменты ───────────────────────────────────── */

function LeadPane({ leadId }: { leadId: string | null }) {
  const { t } = useLocale();
  const [lead, setLead] = useState<Lead | null>(null);
  useEffect(() => {
    setLead(null);
    if (!leadId) return;
    let cancelled = false;
    getLead(leadId)
      .then((l) => !cancelled && setLead(l))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [leadId]);

  const dm = lead?.website_meta?.contact_person ?? null;
  const fact = (label: string, value: React.ReactNode) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "5px 0", borderTop: "1px solid var(--border)", fontSize: 12.5 }}>
      <span style={{ color: "var(--text-dim)", flexShrink: 0 }}>{label}</span>
      <span style={{ textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{value}</span>
    </div>
  );
  const tool = (label: string, hint: string, onClick: () => void, icon: "sparkles" | "check" = "sparkles") => (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 10px",
        border: "1px solid var(--border)",
        borderRadius: 9,
        background: "var(--surface)",
        cursor: "pointer",
        fontSize: 12.5,
        fontWeight: 600,
        color: "var(--text)",
        textAlign: "left",
        width: "100%",
      }}
    >
      <Icon name={icon} size={12} style={{ color: "var(--accent)" }} />
      {label}
      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)", fontWeight: 600 }}>{hint}</span>
    </button>
  );
  const openHenry = () => window.dispatchEvent(new CustomEvent("convioo:open-henry"));

  return (
    <Card padding={16} style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, overflowY: "auto" }}>
      {!leadId && <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>{t("lt.noLead")}</div>}
      {leadId && !lead && <SkeletonLines lines={6} />}
      {lead && (
        <>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 15, fontWeight: 800 }}>{lead.name}</span>
              {typeof lead.score_ai === "number" && <Chip tone={lead.score_ai >= 75 ? "positive" : "default"}>{Math.round(lead.score_ai)}</Chip>}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{[lead.category, lead.address].filter(Boolean).join(" · ")}</div>
          </div>
          {lead.advice && (
            <div style={{ padding: "10px 12px", borderRadius: 10, background: "var(--accent-soft)", border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)", fontSize: 12.5, lineHeight: 1.5 }}>
              <div className="eyebrow" style={{ fontSize: 10, color: "var(--accent)", marginBottom: 3 }}>{t("lt.whyWriting")}</div>
              {lead.advice}
            </div>
          )}
          <div>
            {fact(t("lead.decisionMaker"), dm ? `${dm.name}${dm.title ? ` · ${dm.title}` : ""}` : "—")}
            {fact(t("lt.email"), lead.contact_email ?? dm?.email ?? "—")}
            {fact(t("lt.phone"), lead.phone ?? dm?.phone ?? "—")}
            {fact(t("work.factReviews"), lead.rating != null ? `${lead.rating} · ${lead.reviews_count ?? 0}` : "—")}
            {fact(t("work.factLang"), lead.business_language?.toUpperCase() ?? "—")}
          </div>
          <div>
            <div className="eyebrow" style={{ fontSize: 10, marginBottom: 6 }}>{t("lt.history")}</div>
            <LeadCalls leadId={lead.id} showTitle={false} />
          </div>
          <div style={{ marginTop: "auto", display: "grid", gap: 6 }}>
            <div className="eyebrow" style={{ fontSize: 10, marginBottom: 2 }}>{t("lt.tools")}</div>
            {tool(t("lt.toolHenry"), t("lt.toolHenryHint"), openHenry)}
            <Link href={`/app/leads?lead=${lead.id}`} className="btn btn-ghost btn-sm" style={{ justifyContent: "flex-start" }}>
              {t("inbox.viewLead")}
            </Link>
          </div>
        </>
      )}
    </Card>
  );
}
