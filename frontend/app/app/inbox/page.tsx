"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Icon } from "@/components/Icon";
import { EmptyState } from "@/components/app/EmptyState";
import {
  getInboxThreads,
  getInboxThread,
  replyInThread,
  syncInbox,
  type InboxThreadSummary,
  type InboxThreadDetail,
  type InboxMessage,
} from "@/lib/api";
import { useAbortable, isAbortError } from "@/lib/hooks/useAbortable";
import { useIsMobile } from "@/lib/hooks/useMediaQuery";
import { showError, showSuccess } from "@/lib/toast";
import { useLocale } from "@/lib/i18n";

const MAILBOX_CONNECT_HREF = "/app/settings/integrations";

export default function InboxPage() {
  const { t } = useLocale();
  const isMobile = useIsMobile();
  const newAbort = useAbortable();

  const [connected, setConnected] = useState<boolean | null>(null);
  const [needsReconnect, setNeedsReconnect] = useState(false);
  const [threads, setThreads] = useState<InboxThreadSummary[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(false);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InboxThreadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);

  const [replyBody, setReplyBody] = useState("");
  const [sending, setSending] = useState(false);

  const loadThreads = useCallback(() => {
    const { signal } = newAbort();
    setListLoading(true);
    setListError(false);
    getInboxThreads({ unread: unreadOnly || undefined, limit: 100 }, { signal })
      .then((res) => {
        setConnected(res.connected);
        setNeedsReconnect(res.needs_reconnect);
        setThreads(res.threads);
        setListLoading(false);
      })
      .catch((e) => {
        if (isAbortError(e)) return;
        setListError(true);
        setListLoading(false);
      });
  }, [newAbort, unreadOnly]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  const [detailReloadTick, setDetailReloadTick] = useState(0);

  // Load the selected thread's messages.
  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(false);
    setReplyBody("");
    getInboxThread(activeId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setDetailLoading(false);
        // Once opened, the thread is effectively read — clear its badge
        // locally so the list reflects the user having seen it.
        setThreads((prev) =>
          prev.map((th) =>
            th.thread_id === activeId ? { ...th, unread_count: 0 } : th,
          ),
        );
      })
      .catch((e) => {
        if (cancelled) return;
        if (isAbortError(e)) return;
        setDetailError(true);
        setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, detailReloadTick]);

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const res = await syncInbox();
      setNeedsReconnect(res.needs_reconnect);
      loadThreads();
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  const sendReply = async () => {
    const body = replyBody.trim();
    if (!body || !detail || sending) return;
    setSending(true);
    // Optimistic append of the outbound message.
    const optimistic: InboxMessage = {
      id: `optimistic-${Date.now()}`,
      direction: "outbound",
      from_email: null,
      to_email: detail.messages.find((m) => m.direction === "inbound")?.from_email ?? null,
      subject: detail.subject,
      body_text: body,
      body_html: null,
      sent_at: new Date().toISOString(),
      is_read: true,
    };
    setDetail((d) =>
      d ? { ...d, messages: [...d.messages, optimistic] } : d,
    );
    try {
      await replyInThread(detail.thread_id, body, detail.subject);
      setReplyBody("");
      showSuccess(t("inbox.reply.sent"));
      // Bump the thread's local message count / timestamp.
      setThreads((prev) =>
        prev.map((th) =>
          th.thread_id === detail.thread_id
            ? {
                ...th,
                message_count: th.message_count + 1,
                last_message_at: optimistic.sent_at,
                snippet: body.slice(0, 140),
              }
            : th,
        ),
      );
    } catch (e) {
      // Roll back the optimistic message.
      setDetail((d) =>
        d
          ? { ...d, messages: d.messages.filter((m) => m.id !== optimistic.id) }
          : d,
      );
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  const relative = (ts: string | null): string => {
    if (!ts) return t("common.none");
    const then = new Date(ts).getTime();
    if (Number.isNaN(then)) return t("common.none");
    const diff = Date.now() - then;
    const m = Math.floor(diff / 60000);
    if (m < 1) return t("inbox.relative.now");
    if (m < 60) return t("inbox.relative.m", { n: m });
    const h = Math.floor(m / 60);
    if (h < 24) return t("inbox.relative.h", { n: h });
    const d = Math.floor(h / 24);
    return t("inbox.relative.d", { n: d });
  };

  const totalUnread = useMemo(
    () => threads.reduce((sum, th) => sum + th.unread_count, 0),
    [threads],
  );

  return (
    <>
      <style>{`@keyframes inboxSpin { to { transform: rotate(360deg); } }`}</style>
      <Topbar
        title={t("inbox.title")}
        subtitle={t("inbox.subtitle", { unread: totalUnread })}
        right={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void refresh()}
            disabled={refreshing}
          >
            <span
              style={{
                display: "inline-flex",
                animation: refreshing ? "inboxSpin 0.8s linear infinite" : undefined,
              }}
            >
              <Icon name="rotateCcw" size={14} />
            </span>
            {refreshing ? t("inbox.refreshing") : t("inbox.refresh")}
          </button>
        }
      />
      <div className="page">
        {connected === false && (
          <div
            className="card"
            style={{
              padding: "12px 16px",
              marginBottom: 12,
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Icon name="mail" size={16} style={{ color: "var(--accent)" }} />
            <span style={{ fontSize: 13, color: "var(--text-muted)", flex: 1 }}>
              {t("inbox.connect.hint")}
            </span>
            <Link href={MAILBOX_CONNECT_HREF} className="btn btn-sm">
              {t("inbox.connect.action")}
            </Link>
          </div>
        )}
        {connected === true && needsReconnect && (
          <div
            style={{
              padding: "12px 16px",
              marginBottom: 12,
              borderRadius: 12,
              border: "1px solid color-mix(in srgb, #F59E0B 50%, var(--border))",
              background: "color-mix(in srgb, #F59E0B 12%, var(--surface))",
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Icon name="bell" size={16} style={{ color: "#B45309" }} />
            <span style={{ fontSize: 13, color: "var(--text)", flex: 1 }}>
              {t("inbox.reconnect.banner")}
            </span>
            <Link href={MAILBOX_CONNECT_HREF} className="btn btn-sm">
              {t("inbox.reconnect.action")}
            </Link>
          </div>
        )}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: isMobile
              ? "1fr"
              : "minmax(280px, 360px) 1fr",
            gap: 16,
            alignItems: "start",
          }}
        >
          {/* ── Left: thread list ─────────────────────────────── */}
          {/* On mobile only one pane shows at a time: the list hides once
              a thread is selected so the detail pane takes the screen. */}
          <div
            className="card"
            style={{
              padding: 0,
              overflow: "hidden",
              display: isMobile && activeId ? "none" : "flex",
              flexDirection: "column",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 12px",
                borderBottom: "1px solid var(--border)",
              }}
            >
              <span className="eyebrow" style={{ fontSize: 10 }}>
                {t("inbox.threads.title")}
              </span>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 12,
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={unreadOnly}
                  onChange={(e) => setUnreadOnly(e.target.checked)}
                />
                {t("inbox.filter.unreadOnly")}
              </label>
            </div>

            <div style={{ overflowY: "auto", maxHeight: "calc(100vh - 220px)" }}>
              {listLoading && (
                <div style={{ padding: 24, fontSize: 13, color: "var(--text-muted)" }}>
                  {t("common.loading")}
                </div>
              )}
              {!listLoading && listError && (
                <div style={{ padding: 24, textAlign: "center" }}>
                  <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 10 }}>
                    {t("inbox.error.list")}
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => loadThreads()}
                  >
                    {t("common.retry")}
                  </button>
                </div>
              )}
              {!listLoading && !listError && threads.length === 0 && (
                <div style={{ padding: 24, fontSize: 13, color: "var(--text-muted)", textAlign: "center" }}>
                  {t("inbox.empty.threads")}
                </div>
              )}
              {!listLoading &&
                !listError &&
                threads.map((th) => {
                  const isActive = th.thread_id === activeId;
                  const unread = th.unread_count > 0;
                  const primary = th.lead_name ?? th.counterpart_email ?? t("inbox.unknownSender");
                  return (
                    <button
                      key={th.thread_id}
                      type="button"
                      onClick={() => setActiveId(th.thread_id)}
                      style={{
                        display: "block",
                        width: "100%",
                        textAlign: "left",
                        padding: "12px 14px",
                        borderBottom: "1px solid var(--border)",
                        borderLeft: isActive
                          ? "2px solid var(--accent)"
                          : "2px solid transparent",
                        background: isActive ? "var(--surface-2)" : "transparent",
                        cursor: "pointer",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          marginBottom: 3,
                        }}
                      >
                        {unread && (
                          <span
                            aria-hidden
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: "var(--accent)",
                              flexShrink: 0,
                            }}
                          />
                        )}
                        <span
                          style={{
                            fontSize: 13.5,
                            fontWeight: unread ? 700 : 600,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            flex: 1,
                            minWidth: 0,
                          }}
                        >
                          {primary}
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            color: "var(--text-dim)",
                            flexShrink: 0,
                          }}
                        >
                          {relative(th.last_message_at)}
                        </span>
                      </div>
                      <div
                        style={{
                          fontSize: 12.5,
                          fontWeight: unread ? 600 : 500,
                          color: "var(--text)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          marginBottom: 2,
                        }}
                      >
                        {th.subject || t("inbox.noSubject")}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 12,
                            color: "var(--text-muted)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            flex: 1,
                            minWidth: 0,
                          }}
                        >
                          {th.snippet || ""}
                        </span>
                        {unread && (
                          <span
                            className="chip"
                            style={{
                              fontSize: 10,
                              padding: "1px 6px",
                              background: "var(--accent)",
                              color: "white",
                              borderColor: "transparent",
                              flexShrink: 0,
                            }}
                          >
                            {th.unread_count}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
            </div>
          </div>

          {/* ── Right: thread detail ──────────────────────────── */}
          {/* On mobile this pane only appears once a thread is selected;
              otherwise the list above occupies the screen. */}
          <div
            className="card"
            style={{
              padding: 0,
              display: isMobile && !activeId ? "none" : "flex",
              flexDirection: "column",
              minHeight: "calc(100vh - 200px)",
            }}
          >
            {!activeId && (
              <div style={{ margin: "auto", padding: 24 }}>
                <EmptyState
                  icon="mail"
                  title={t("inbox.detail.emptyTitle")}
                  body={t("inbox.detail.emptyBody")}
                />
              </div>
            )}
            {activeId && detailLoading && (
              <div style={{ padding: 24, fontSize: 13, color: "var(--text-muted)" }}>
                {t("common.loading")}
              </div>
            )}
            {activeId && !detailLoading && detailError && (
              <div style={{ margin: "auto", padding: 24, textAlign: "center" }}>
                <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 10 }}>
                  {t("inbox.error.thread")}
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setDetailReloadTick((n) => n + 1)}
                >
                  {t("common.retry")}
                </button>
              </div>
            )}
            {activeId && !detailLoading && !detailError && detail && (
              <>
                <div
                  style={{
                    padding: "14px 18px",
                    borderBottom: "1px solid var(--border)",
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  {isMobile && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setActiveId(null)}
                      style={{ flexShrink: 0 }}
                    >
                      {t("inbox.backToList")}
                    </button>
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 600 }}>
                      {detail.subject || t("inbox.noSubject")}
                    </div>
                  </div>
                  {detail.lead_id && (
                    <Link
                      href="/app/leads"
                      className="btn btn-ghost btn-sm"
                    >
                      <Icon name="user" size={13} /> {t("inbox.viewLead")}
                    </Link>
                  )}
                </div>

                <div
                  style={{
                    flex: 1,
                    overflowY: "auto",
                    padding: 18,
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                  }}
                >
                  {detail.messages.map((m) => (
                    <MessageBubble key={m.id} message={m} relative={relative} />
                  ))}
                </div>

                <div
                  style={{
                    borderTop: "1px solid var(--border)",
                    padding: 14,
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <textarea
                    className="input"
                    value={replyBody}
                    onChange={(e) => setReplyBody(e.target.value)}
                    placeholder={t("inbox.reply.placeholder")}
                    rows={3}
                    onKeyDown={(e) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                        e.preventDefault();
                        void sendReply();
                      }
                    }}
                    style={{ resize: "vertical", fontSize: 13.5 }}
                  />
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => void sendReply()}
                      disabled={sending || !replyBody.trim()}
                    >
                      <Icon name="send" size={13} />
                      {sending ? t("inbox.reply.sending") : t("inbox.reply.send")}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function MessageBubble({
  message,
  relative,
}: {
  message: InboxMessage;
  relative: (ts: string | null) => string;
}) {
  const { t } = useLocale();
  const [showHtml, setShowHtml] = useState(false);
  const outbound = message.direction === "outbound";
  const hasHtml = Boolean(message.body_html);
  const hasText = Boolean(message.body_text);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: outbound ? "flex-end" : "flex-start",
      }}
    >
      <div
        style={{
          maxWidth: "78%",
          minWidth: 0,
          borderRadius: 12,
          padding: "10px 14px",
          background: outbound
            ? "color-mix(in srgb, var(--accent) 14%, var(--surface))"
            : "var(--surface-2)",
          border: outbound
            ? "1px solid color-mix(in srgb, var(--accent) 30%, var(--border))"
            : "1px solid var(--border)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            marginBottom: 6,
            fontSize: 11,
            color: "var(--text-dim)",
          }}
        >
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {outbound
              ? t("inbox.message.to", { email: message.to_email ?? t("common.none") })
              : t("inbox.message.from", { email: message.from_email ?? t("common.none") })}
          </span>
          <span style={{ flexShrink: 0 }}>{relative(message.sent_at)}</span>
        </div>

        {showHtml && hasHtml ? (
          // Provider HTML is untrusted — render in a sandboxed iframe via
          // srcDoc. ``sandbox`` with no ``allow-scripts`` neutralises any
          // embedded JS, and the empty sandbox blocks same-origin access,
          // form submits and top-navigation. Never dangerouslySetInnerHTML.
          <iframe
            title={t("inbox.message.htmlFrame")}
            sandbox=""
            srcDoc={message.body_html ?? ""}
            style={{
              width: "100%",
              minHeight: 200,
              border: "1px solid var(--border)",
              borderRadius: 8,
              background: "white",
            }}
          />
        ) : (
          <div
            style={{
              fontSize: 13.5,
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: "var(--text)",
            }}
          >
            {hasText
              ? message.body_text
              : hasHtml
                ? t("inbox.message.htmlOnly")
                : t("inbox.message.empty")}
          </div>
        )}

        {hasHtml && (
          <button
            type="button"
            onClick={() => setShowHtml((v) => !v)}
            style={{
              marginTop: 6,
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              fontSize: 11.5,
              color: "var(--accent)",
            }}
          >
            {showHtml ? t("inbox.message.showText") : t("inbox.message.showOriginal")}
          </button>
        )}
      </div>
    </div>
  );
}
