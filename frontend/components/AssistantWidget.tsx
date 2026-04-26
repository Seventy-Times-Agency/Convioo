"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { HenryAvatar } from "@/components/HenryAvatar";
import {
  ApiError,
  assistantChat,
  updateMyProfile,
  updateTeam,
  updateTeamMember,
  type AssistantField,
  type AssistantMode,
  type AssistantProfileSuggestion,
  type AssistantTeamSuggestion,
  type ConsultMessage,
  type UserProfileUpdate,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import {
  activeTeamId,
  getActiveWorkspace,
  subscribeWorkspace,
  type Workspace,
} from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const STORAGE_KEY_BASE = "convioo.henry.history";
const MAX_HISTORY = 30;

function storageKeyFor(workspace: Workspace): string {
  return workspace.kind === "team"
    ? `${STORAGE_KEY_BASE}.team.${workspace.team_id}`
    : `${STORAGE_KEY_BASE}.personal`;
}

interface ChatMsg extends ConsultMessage {
  /** Optional profile change Henry suggested with this assistant turn. */
  suggestion?: AssistantProfileSuggestion | null;
  team_suggestion?: AssistantTeamSuggestion | null;
  suggestion_summary?: string | null;
  applied?: boolean;
  mode?: AssistantMode;
  /** Profile field Henry was waiting on after THIS turn. Echoed back
   *  on the next user turn so a short reply (e.g. "Berlin") gets
   *  routed to the field he asked about. */
  awaiting_field?: AssistantField | null;
}

const AGE_LABEL_KEY: Record<string, TranslationKey> = {
  "<18": "onboarding.age.lt18",
  "18-24": "onboarding.age.18_24",
  "25-34": "onboarding.age.25_34",
  "35-44": "onboarding.age.35_44",
  "45-54": "onboarding.age.45_54",
  "55+": "onboarding.age.55plus",
};

const SIZE_LABEL_KEY: Record<string, TranslationKey> = {
  solo: "onboarding.size.solo",
  small: "onboarding.size.small",
  medium: "onboarding.size.medium",
  large: "onboarding.size.large",
};

/**
 * Floating in-product assistant.
 *
 * Closed: 60×60 round avatar fixed in the bottom-right corner.
 * Open: a 380×560 chat panel anchored to the same corner. Stays on
 * screen across navigations (parent mounts it on the workspace
 * layout). Conversation history persists in localStorage so the user
 * can pop the widget open later and continue.
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

  // Slot Henry was waiting on after the latest assistant turn — kept
  // in component state so it's available on the very next send call
  // even if React hasn't flushed the messages array yet.
  const lastAwaitingField = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && m.awaiting_field !== undefined) {
        return m.awaiting_field ?? null;
      }
    }
    return null;
  })();

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;
    const next: ChatMsg[] = [
      ...messages,
      { role: "user", content: trimmed },
    ];
    setMessages(next);
    setDraft("");
    setThinking(true);
    try {
      const reply = await assistantChat(
        next.map(({ role, content }) => ({ role, content })),
        {
          teamId: activeTeamId(),
          awaitingField: lastAwaitingField,
        },
      );
      const incoming: ChatMsg = {
        role: "assistant",
        content: reply.reply,
        mode: reply.mode,
        suggestion: reply.profile_suggestion,
        team_suggestion: reply.team_suggestion,
        suggestion_summary: reply.suggestion_summary,
        awaiting_field: reply.awaiting_field,
        applied: false,
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

  const applySuggestion = async (idx: number) => {
    const msg = messages[idx];
    const sg = msg?.suggestion;
    if (!sg) return;
    const patch: UserProfileUpdate = {};
    if (sg.display_name) patch.display_name = sg.display_name;
    if (sg.age_range) patch.age_range = sg.age_range;
    if (sg.business_size) patch.business_size = sg.business_size;
    if (sg.service_description)
      patch.service_description = sg.service_description;
    if (sg.home_region) patch.home_region = sg.home_region;
    if (sg.niches && sg.niches.length > 0) patch.niches = sg.niches;
    if (Object.keys(patch).length === 0) return;

    try {
      await updateMyProfile(patch);
      setMessages((all) => [
        ...all.map((m, i) => (i === idx ? { ...m, applied: true } : m)),
        { role: "assistant", content: t("assistant.applied") },
      ]);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setMessages((all) => [
        ...all,
        {
          role: "assistant",
          content: t("assistant.applyError", { detail }),
        },
      ]);
    }
  };

  const applyTeamSuggestion = async (idx: number) => {
    const msg = messages[idx];
    const sg = msg?.team_suggestion;
    if (!sg || workspace.kind !== "team") return;
    const teamId = workspace.team_id;
    try {
      if (sg.description !== undefined && sg.description !== null) {
        await updateTeam(teamId, { description: sg.description });
      }
      if (sg.member_descriptions && sg.member_descriptions.length > 0) {
        for (const m of sg.member_descriptions) {
          await updateTeamMember(teamId, m.user_id, {
            description: m.description,
          });
        }
      }
      setMessages((all) => [
        ...all.map((m, i) => (i === idx ? { ...m, applied: true } : m)),
        { role: "assistant", content: t("assistant.applied") },
      ]);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setMessages((all) => [
        ...all,
        {
          role: "assistant",
          content: t("assistant.applyError", { detail }),
        },
      ]);
    }
  };

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
                {thinking
                  ? t("assistant.thinking")
                  : t("assistant.role")}
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
            {messages.map((m, i) => (
              <AssistantMessage
                key={i}
                msg={m}
                onApplyProfile={() => applySuggestion(i)}
                onApplyTeam={() => applyTeamSuggestion(i)}
              />
            ))}
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
  onApplyProfile,
  onApplyTeam,
}: {
  msg: ChatMsg;
  onApplyProfile: () => void;
  onApplyTeam: () => void;
}) {
  const { t } = useLocale();
  const isBot = msg.role === "assistant";
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
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: "82%" }}>
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
        {isBot && msg.suggestion && !msg.applied && (
          <SuggestionCard
            suggestion={msg.suggestion}
            summary={msg.suggestion_summary ?? undefined}
            onApply={onApplyProfile}
          />
        )}
        {isBot && msg.team_suggestion && !msg.applied && (
          <TeamSuggestionCard
            suggestion={msg.team_suggestion}
            summary={msg.suggestion_summary ?? undefined}
            onApply={onApplyTeam}
          />
        )}
        {isBot && msg.applied && (
          <div
            style={{
              fontSize: 11,
              color: "var(--hot)",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Icon name="check" size={11} /> {t("assistant.applied")}
          </div>
        )}
      </div>
    </div>
  );
}

function SuggestionCard({
  suggestion,
  summary,
  onApply,
}: {
  suggestion: AssistantProfileSuggestion;
  summary?: string;
  onApply: () => void;
}) {
  const { t } = useLocale();
  const items: { label: string; value: string }[] = [];
  if (suggestion.display_name)
    items.push({
      label: t("profile.field.displayName"),
      value: suggestion.display_name,
    });
  if (suggestion.age_range)
    items.push({
      label: t("profile.field.age"),
      value: t(
        AGE_LABEL_KEY[suggestion.age_range] ?? ("profile.empty" as TranslationKey),
      ),
    });
  if (suggestion.business_size)
    items.push({
      label: t("profile.field.business"),
      value: t(
        SIZE_LABEL_KEY[suggestion.business_size] ??
          ("profile.empty" as TranslationKey),
      ),
    });
  if (suggestion.service_description)
    items.push({
      label: t("profile.field.offer"),
      value: suggestion.service_description,
    });
  if (suggestion.home_region)
    items.push({
      label: t("profile.field.region"),
      value: suggestion.home_region,
    });
  if (suggestion.niches && suggestion.niches.length > 0)
    items.push({
      label: t("profile.field.niches"),
      value: suggestion.niches.join(", "),
    });

  if (items.length === 0) return null;

  return (
    <div
      style={{
        padding: 10,
        background: "var(--surface)",
        border: "1px solid color-mix(in srgb, var(--accent) 25%, var(--border))",
        borderRadius: 10,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div
        className="eyebrow"
        style={{ fontSize: 9, color: "var(--accent)", marginBottom: 2 }}
      >
        {t("assistant.suggestion")}
      </div>
      {summary && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.45 }}>
          {summary}
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {items.map((it) => (
          <div
            key={it.label}
            style={{ fontSize: 12, lineHeight: 1.4 }}
          >
            <span style={{ color: "var(--text-dim)" }}>{it.label}:</span>{" "}
            <span style={{ color: "var(--text)" }}>{it.value}</span>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-sm"
        onClick={onApply}
        style={{ alignSelf: "flex-start", marginTop: 4 }}
      >
        <Icon name="check" size={12} /> {t("assistant.apply")}
      </button>
    </div>
  );
}

function TeamSuggestionCard({
  suggestion,
  summary,
  onApply,
}: {
  suggestion: AssistantTeamSuggestion;
  summary?: string;
  onApply: () => void;
}) {
  const { t } = useLocale();
  const items: { label: string; value: string }[] = [];
  if (suggestion.description) {
    items.push({
      label: t("assistant.team.descriptionLabel"),
      value: suggestion.description,
    });
  }
  if (suggestion.member_descriptions) {
    for (const m of suggestion.member_descriptions) {
      items.push({
        label: t("assistant.team.memberLabel", { id: m.user_id }),
        value: m.description,
      });
    }
  }
  if (items.length === 0) return null;

  return (
    <div
      style={{
        padding: 10,
        background: "var(--surface)",
        border: "1px solid color-mix(in srgb, var(--accent) 25%, var(--border))",
        borderRadius: 10,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div
        className="eyebrow"
        style={{ fontSize: 9, color: "var(--accent)", marginBottom: 2 }}
      >
        {t("assistant.team.suggestion")}
      </div>
      {summary && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.45 }}>
          {summary}
        </div>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {items.map((it) => (
          <div key={it.label} style={{ fontSize: 12, lineHeight: 1.45 }}>
            <span style={{ color: "var(--text-dim)" }}>{it.label}:</span>{" "}
            <span style={{ color: "var(--text)" }}>{it.value}</span>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-sm"
        onClick={onApply}
        style={{ alignSelf: "flex-start", marginTop: 4 }}
      >
        <Icon name="check" size={12} /> {t("assistant.apply")}
      </button>
    </div>
  );
}
