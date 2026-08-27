"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import {
  clearAssistantMemory,
  listAssistantMemory,
  type AssistantMemoryItem,
} from "@/lib/api";
import { useLocale } from "@/lib/i18n";
import { showError } from "@/lib/toast";

export function HenryMemorySection() {
  const { t } = useLocale();
  const [items, setItems] = useState<AssistantMemoryItem[] | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listAssistantMemory()
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
      })
      .catch((e) => {
        if (cancelled) return;
        showError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onClear = async () => {
    setClearing(true);
    try {
      await clearAssistantMemory();
      setItems([]);
      setConfirmingClear(false);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setClearing(false);
    }
  };

  if (items === null) return null;

  return (
    <div className="card" style={{ padding: 20, marginTop: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <div className="eyebrow">{t("profile.memory.title")}</div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              marginTop: 4,
              lineHeight: 1.5,
            }}
          >
            {t("profile.memory.subtitle")}
          </div>
        </div>
        {(items?.length ?? 0) > 0 &&
          (confirmingClear ? (
            <div style={{ display: "flex", gap: 6 }}>
              <button
                type="button"
                className="btn btn-sm"
                onClick={onClear}
                disabled={clearing}
                style={{ background: "var(--cold)", color: "white" }}
              >
                {clearing ? t("common.loading") : t("profile.memory.confirm")}
              </button>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setConfirmingClear(false)}
                disabled={clearing}
              >
                {t("common.cancel")}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setConfirmingClear(true)}
            >
              <Icon name="x" size={13} />
              {t("profile.memory.clear")}
            </button>
          ))}
      </div>

      {items && items.length === 0 ? (
        <div
          style={{
            fontSize: 13,
            color: "var(--text-dim)",
            lineHeight: 1.5,
          }}
        >
          {t("profile.memory.empty")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {(items ?? []).slice(0, 8).map((m) => (
            <div
              key={m.id}
              style={{
                padding: "10px 12px",
                background: "var(--surface-2)",
                borderRadius: 8,
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--text)",
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
              }}
            >
              <span
                style={{
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color:
                    m.kind === "summary" ? "var(--accent)" : "var(--text-muted)",
                  marginTop: 3,
                  flexShrink: 0,
                  minWidth: 56,
                }}
              >
                {m.kind === "summary"
                  ? t("profile.memory.kind.summary")
                  : t("profile.memory.kind.fact")}
              </span>
              <span style={{ flex: 1 }}>{m.content}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
