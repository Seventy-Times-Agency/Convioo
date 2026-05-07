"use client";

import { Icon } from "@/components/Icon";
import { HenryAvatar } from "@/components/HenryAvatar";
import { useLocale } from "@/lib/i18n";
import type { ChatMsg } from "./types";

function ChatBubble({ msg }: { msg: ChatMsg }) {
  const isBot = msg.role === "assistant";
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        flexDirection: isBot ? "row" : "row-reverse",
      }}
    >
      {isBot ? (
        <HenryAvatar size={28} />
      ) : (
        <div
          className="avatar avatar-sm"
          style={{ background: "var(--accent)" }}
        >
          ·
        </div>
      )}
      <div
        style={{
          maxWidth: "82%",
          padding: "10px 14px",
          background: isBot ? "var(--surface-2)" : "var(--accent)",
          color: isBot ? "var(--text)" : "white",
          border: isBot ? "1px solid var(--border)" : "none",
          borderRadius: 14,
          borderTopLeftRadius: isBot ? 4 : 14,
          borderTopRightRadius: isBot ? 14 : 4,
          fontSize: 13.5,
          lineHeight: 1.55,
          whiteSpace: "pre-wrap",
        }}
      >
        {msg.content}
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: number }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: "var(--text-muted)",
        animation: `lumen-pulse 1s ${delay}ms infinite ease-in-out`,
      }}
    />
  );
}

export function ThinkingBubble() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <HenryAvatar size={28} />
      <div
        style={{
          padding: "10px 14px",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          borderTopLeftRadius: 4,
          display: "flex",
          gap: 4,
          alignItems: "center",
        }}
      >
        <Dot delay={0} />
        <Dot delay={120} />
        <Dot delay={240} />
      </div>
    </div>
  );
}

export function ChatColumn({
  messages,
  thinking,
  draft,
  onDraftChange,
  onSubmit,
  chatRef,
}: {
  messages: ChatMsg[];
  thinking: boolean;
  draft: string;
  onDraftChange: (v: string) => void;
  onSubmit: () => void;
  chatRef: React.RefObject<HTMLDivElement>;
}) {
  const { t } = useLocale();

  return (
    <div
      className="card"
      style={{
        padding: 0,
        display: "flex",
        flexDirection: "column",
        height: "calc(100vh - 140px)",
        minHeight: 560,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "18px 22px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 12,
          background:
            "linear-gradient(135deg, color-mix(in srgb, var(--accent) 6%, var(--surface)), var(--surface))",
        }}
      >
        <HenryAvatar size={40} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Henry</div>
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
            {thinking ? t("search.consult.thinking") : t("search.consult.role")}
          </div>
        </div>
      </div>

      <div
        ref={chatRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px 22px",
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        {messages.map((m, i) => (
          <ChatBubble key={i} msg={m} />
        ))}
        {thinking && <ThinkingBubble />}
      </div>

      <div
        style={{
          padding: "14px 16px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          gap: 8,
          background: "var(--surface)",
        }}
      >
        <input
          className="input"
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={t("search.consult.placeholder")}
          disabled={thinking}
        />
        <button
          type="button"
          className="btn btn-icon"
          onClick={onSubmit}
          disabled={thinking || !draft.trim()}
          style={{
            background: "var(--accent)",
            color: "white",
            width: 40,
            height: 40,
            opacity: thinking || !draft.trim() ? 0.5 : 1,
          }}
        >
          <Icon name="send" size={16} />
        </button>
      </div>
    </div>
  );
}
