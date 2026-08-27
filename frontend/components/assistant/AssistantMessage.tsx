"use client";

import { Icon } from "@/components/Icon";
import { HenryAvatar } from "@/components/HenryAvatar";
import type { PendingAction } from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import type { ChatMsg } from "./types";

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

export function AssistantMessage({
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
