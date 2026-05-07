"use client";

import { Icon } from "@/components/Icon";
import { useLocale } from "@/lib/i18n";

export function AssistantInput({
  draft,
  thinking,
  onDraftChange,
  onSend,
}: {
  draft: string;
  thinking: boolean;
  onDraftChange: (v: string) => void;
  onSend: (text: string) => void;
}) {
  const { t } = useLocale();

  return (
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
        onChange={(e) => onDraftChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend(draft);
          }
        }}
        placeholder={t("assistant.placeholder")}
        disabled={thinking}
        style={{ fontSize: 13.5 }}
      />
      <button
        type="button"
        className="btn btn-icon"
        onClick={() => onSend(draft)}
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
  );
}
