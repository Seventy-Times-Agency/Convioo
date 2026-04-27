"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { HenryAvatar } from "@/components/HenryAvatar";
import {
  ApiError,
  assistantChat,
  type AssistantField,
  type AssistantMode,
  type ConsultMessage,
  type PendingAction,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import {
  activeTeamId,
  getActiveWorkspace,
  subscribeWorkspace,
  type Workspace,
} from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

const STORAGE_KEY_BASE = "convioo.henry.history";
const MAX_HISTORY = 30;

function storageKeyFor(workspace: Workspace): string {
  return workspace.kind === "team"
    ? `${STORAGE_KEY_BASE}.team.${workspace.team_id}`
    : `${STORAGE_KEY_BASE}.personal`;
}

interface ChatMsg extends ConsultMessage {
  mode?: AssistantMode;
  /** Profile field Henry was waiting on after THIS turn. Echoed back
   *  on the next user turn so a short reply (e.g. "Berlin") gets
   *  routed to the field he asked about. */
  awaiting_field?: AssistantField | null;
  /** Confirm-before-write: actions Henry proposed on this turn,
   *  awaiting an in-chat confirmation from the user. */
  pending_actions?: PendingAction[] | null;
  /** Filled when Henry's previous turn proposed actions and the user
   *  confirmed them — replaces the pending card with a "записано" mark. */
  applied_actions?: PendingAction[] | null;
  /** Optional 1-liner Henry attached to a pending proposal. */
  suggestion_summary?: string | null;
  /** Set after the user clicks dismiss on the pending card; hides the
   *  buttons so the same card can't be re-confirmed. */
  resolved?: "applied" | "dismissed";
}

/**
 * Floating in-product assistant — Henry.
 *
 * Closed: 60×60 round avatar fixed in the bottom-right corner.
 * Open: a 380×560 chat panel anchored to the same corner.
 *
 * Confirm-before-write: Henry never mutates the profile or team
 * silently. He returns ``pending_actions`` (rendered as inline cards
 * with confirm / dismiss buttons). The user either clicks confirm or
 * types «да» / «нет» — the backend keyword-detects the reply and
 * applies the actions on the next round-trip.
 */
export function AssistantWidget() {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>({ kind: "personal" });
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [unread, setUnread] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSignedIn(getCurrentUser() !== null);
    setWorkspace(getActiveWorkspace());
    return subscribeWorkspace(() => setWorkspace(getActiveWorkspace()));
  }, []);

  // Per-workspace history: switching personal ↔ team flips the chat
  // so the team consultation isn't mixed with personal-profile help.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(storageKeyFor(workspace));
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setMessages(parsed.slice(-MAX_HISTORY));
          return;
        }
      }
    } catch {
      // fall through
    }
    setMessages([]);
  }, [workspace]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(
        storageKeyFor(workspace),
        JSON.stringify(messages.slice(-MAX_HISTORY)),
      );
    } catch {
      // quota / disabled
    }
  }, [messages, workspace]);

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [open, messages, thinking]);

  useEffect(() => {
    if (open) setUnread(0);
  }, [open]);

  // Other surfaces (e.g. ProfileNudgeBanner) can pop the widget open
  // by dispatching this event — keeps the trigger decoupled from the
  // widget's internal state.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onOpen = () => setOpen(true);
    window.addEventListener("convioo:open-henry", onOpen);
    return () => window.removeEventListener("convioo:open-henry", onOpen);
  }, []);

  // Latest assistant turn drives what context we ship back to the
  // server: which slot Henry is waiting on, and which actions are
  // currently pending confirmation.
  const lastAssistantContext = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== "assistant") continue;
      return {
        awaitingField: m.awaiting_field ?? null,
        pendingActions: m.resolved ? null : m.pending_actions ?? null,
      };
    }
    return { awaitingField: null, pendingActions: null };
  }, [messages]);

  if (!signedIn) return null;

  const greet = (): ChatMsg => ({
    role: "assistant",
    content:
      workspace.kind === "team"
        ? t("assistant.greeting.team", { team: workspace.team_name })
        : t("assistant.greeting"),
  });

  const openWithGreeting = () => {
    setOpen(true);
    if (messages.length === 0) {
      setMessages([greet()]);
    }
  };

  const sendRaw = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;
    const next: ChatMsg[] = [...messages, { role: "user", content: trimmed }];
    // Mark the previous pending card as "resolved" the moment the user
    // sends a follow-up — backend will apply or refuse based on the
    // text, and we don't want the card to flash buttons again.
    const withResolved = next.map((m, i) =>
      i === next.length - 1 ||
      m.role !== "assistant" ||
      !m.pending_actions ||
      m.resolved
        ? m
        : { ...m, resolved: "dismissed" as const },
    );
    setMessages(withResolved);
    setDraft("");
    setThinking(true);
    try {
      const reply = await assistantChat(
        next.map(({ role, content }) => ({ role, content })),
        {
          teamId: activeTeamId(),
          awaitingField: lastAssistantContext.awaitingField,
          pendingActions: lastAssistantContext.pendingActions,
        },
      );
      const incoming: ChatMsg = {
        role: "assistant",
        content: reply.reply,
        mode: reply.mode,
        awaiting_field: reply.awaiting_field,
        pending_actions: reply.pending_actions,
        applied_actions: reply.applied_actions,
        suggestion_summary: reply.suggestion_summary,
      };
      setMessages((m) => [...m, incoming]);
      if (!open) setUnread((n) => n + 1);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: t("assistant.error", { detail }),
        },
      ]);
    } finally {
      setThinking(false);
    }
  };

  const send = (text: string) => sendRaw(text);

  // Confirm/dismiss button on a pending card just sends the equivalent
  // chat keyword; backend handles "да" / "нет" identically whether they
  // came from a click or were typed by the user.
  const confirmPending = () => sendRaw("да");
  const dismissPending = () => sendRaw("нет");

  const reset = () => {
    setMessages([greet()]);
  };

  return (
    <>
      <style>{`
        @keyframes henry-pulse {
          0%, 80%, 100% { opacity: 0.35; transform: scale(.85); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>

      {!open && (
        <button
          type="button"
          aria-label={t("assistant.open")}
          onClick={openWithGreeting}
          style={{
            position: "fixed",
            right: 24,
            bottom: 24,
            zIndex: 90,
            width: 60,
            height: 60,
            borderRadius: "50%",
            border: "none",
            padding: 0,
            background: "transparent",
            cursor: "pointer",
            boxShadow:
              "0 12px 28px rgba(15,15,20,0.18), 0 0 0 1px var(--border)",
          }}
        >
          <HenryAvatar size={60} />
          <span
            style={{
              position: "absolute",
              right: 2,
              bottom: 2,
              width: 14,
              height: 14,
              borderRadius: "50%",
              background: "#16A34A",
              border: "2px solid var(--surface)",
            }}
          />
          {unread > 0 && (
            <span
              style={{
                position: "absolute",
                top: -4,
                right: -4,
                minWidth: 20,
                height: 20,
                padding: "0 6px",
                borderRadius: 10,
                background: "var(--accent)",
                color: "white",
                fontSize: 11,
                fontWeight: 700,
                display: "grid",
                placeItems: "center",
              }}
            >
              {unread}
            </span>
          )}
        </button>
      )}

      {open && (
        <div
          role="dialog"
          aria-label="Henry"
          style={{
            position: "fixed",
            right: 24,
            bottom: 24,
            zIndex: 95,
            width: 380,
            maxWidth: "calc(100vw - 32px)",
            height: 560,
            maxHeight: "calc(100vh - 80px)",
            background: "var(--surface)",
            borderRadius: 16,
            boxShadow:
              "0 20px 50px rgba(15,15,20,0.22), 0 0 0 1px var(--border)",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "14px 16px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              gap: 10,
              background:
                "linear-gradient(135deg, color-mix(in srgb, var(--accent) 6%, var(--surface)), var(--surface))",
            }}
          >
            <HenryAvatar size={36} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>Henry</div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span
                  className="status-dot live"
                  style={{ width: 6, height: 6 }}
                />
                {thinking ? t("assistant.thinking") : t("assistant.role")}
              </div>
            </div>
            <button
              type="button"
              onClick={reset}
              title={t("assistant.reset")}
              style={{
                background: "none",
                border: "none",
                color: "var(--text-dim)",
                cursor: "pointer",
                padding: 6,
                marginRight: 2,
              }}
            >
              <Icon name="x" size={14} />
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label={t("assistant.close")}
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                cursor: "pointer",
                padding: 6,
              }}
            >
              <Icon name="chevronDown" size={14} />
            </button>
          </div>

          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "14px 14px 6px",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {messages.map((m, i) => {
              const isLastAssistant =
                i === messages.length - 1 && m.role === "assistant";
              return (
                <AssistantMessage
                  key={i}
                  msg={m}
                  active={isLastAssistant && !thinking}
                  onConfirm={confirmPending}
                  onDismiss={dismissPending}
                />
              );
            })}
            {thinking && (
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <HenryAvatar size={24} />
                <div
                  style={{
                    padding: "8px 12px",
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    borderTopLeftRadius: 4,
                    display: "flex",
                    gap: 4,
                  }}
                >
                  {[0, 120, 240].map((d) => (
                    <span
                      key={d}
                      style={{
                        width: 5,
                        height: 5,
                        borderRadius: "50%",
                        background: "var(--text-muted)",
                        animation: `henry-pulse 1s ${d}ms infinite ease-in-out`,
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          <div
            style={{
              padding: 10,
              borderTop: "1px solid var(--border)",
              display: "flex",
              gap: 6,
            }}
          >
            <input
              className="input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(draft);
                }
              }}
              placeholder={t("assistant.placeholder")}
              disabled={thinking}
              style={{ fontSize: 13.5 }}
            />
            <button
              type="button"
              className="btn btn-icon"
              onClick={() => send(draft)}
              disabled={thinking || !draft.trim()}
              style={{
                background: "var(--accent)",
                color: "white",
                opacity: thinking || !draft.trim() ? 0.5 : 1,
              }}
            >
              <Icon name="send" size={14} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function AssistantMessage({
  msg,
  active,
  onConfirm,
  onDismiss,
}: {
  msg: ChatMsg;
  active: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  const { t } = useLocale();
  const isBot = msg.role === "assistant";
  const showPendingButtons = active && !msg.resolved && (msg.pending_actions?.length ?? 0) > 0;
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "flex-start",
        flexDirection: isBot ? "row" : "row-reverse",
      }}
    >
      {isBot ? (
        <HenryAvatar size={24} />
      ) : (
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: "50%",
            background: "var(--accent)",
            display: "grid",
            placeItems: "center",
            color: "white",
            fontSize: 11,
            fontWeight: 700,
          }}
        >
          ·
        </div>
      )}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          maxWidth: "82%",
        }}
      >
        <div
          style={{
            padding: "8px 12px",
            background: isBot ? "var(--surface-2)" : "var(--accent)",
            color: isBot ? "var(--text)" : "white",
            border: isBot ? "1px solid var(--border)" : "none",
            borderRadius: 12,
            borderTopLeftRadius: isBot ? 4 : 12,
            borderTopRightRadius: isBot ? 12 : 4,
            fontSize: 13,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          {msg.content}
        </div>

        {isBot && (msg.pending_actions?.length ?? 0) > 0 && (
          <PendingActionsCard
            actions={msg.pending_actions ?? []}
            summary={msg.suggestion_summary ?? undefined}
            showButtons={showPendingButtons}
            onConfirm={onConfirm}
            onDismiss={onDismiss}
          />
        )}

        {isBot && (msg.applied_actions?.length ?? 0) > 0 && (
          <AppliedActionsCard actions={msg.applied_actions ?? []} />
        )}
      </div>
    </div>
  );
}

function PendingActionsCard({
  actions,
  summary,
  showButtons,
  onConfirm,
  onDismiss,
}: {
  actions: PendingAction[];
  summary?: string;
  showButtons: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}) {
  const { t } = useLocale();
  return (
    <div
      style={{
        padding: 10,
        background: "var(--surface)",
        border:
          "1px solid color-mix(in srgb, var(--accent) 25%, var(--border))",
        borderRadius: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div
        className="eyebrow"
        style={{ fontSize: 9, color: "var(--accent)" }}
      >
        {t("assistant.pending.title")}
      </div>
      {summary && (
        <div
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            lineHeight: 1.45,
          }}
        >
          {summary}
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {actions.map((a, i) => (
          <div
            key={i}
            style={{
              fontSize: 12,
              lineHeight: 1.45,
              color: "var(--text)",
            }}
          >
            • {a.summary}
          </div>
        ))}
      </div>
      {showButtons && (
        <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
          <button
            type="button"
            className="btn btn-sm"
            onClick={onConfirm}
            style={{ flex: 1, justifyContent: "center" }}
          >
            <Icon name="check" size={12} /> {t("assistant.pending.confirm")}
          </button>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={onDismiss}
            style={{ justifyContent: "center" }}
          >
            {t("assistant.pending.dismiss")}
          </button>
        </div>
      )}
    </div>
  );
}

function AppliedActionsCard({ actions }: { actions: PendingAction[] }) {
  const { t } = useLocale();
  // Special-case launch_search: surface an "Open session" link to the
  // newly created session — that's the whole point of letting Henry
  // launch from chat.
  const launched = actions.find(
    (a) => a.kind === "launch_search" && (a.payload as { search_id?: string }).search_id,
  );
  if (launched) {
    const sid = (launched.payload as { search_id?: string }).search_id;
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 11.5,
          color: "var(--hot)",
        }}
      >
        <Icon name="check" size={11} /> {t("assistant.launchedSearch")}
        {sid && (
          <a
            href={`/app/sessions/${sid}`}
            style={{
              color: "var(--accent)",
              fontWeight: 600,
              marginLeft: 6,
            }}
          >
            {t("assistant.openSession")} →
          </a>
        )}
      </div>
    );
  }
  return (
    <div
      style={{
        fontSize: 11.5,
        color: "var(--hot)",
        display: "flex",
        alignItems: "center",
        gap: 4,
      }}
    >
      <Icon name="check" size={11} /> {t("assistant.applied")}
    </div>
  );
}
