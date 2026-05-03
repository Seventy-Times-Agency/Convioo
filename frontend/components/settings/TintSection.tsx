"use client";

import { useEffect, useState } from "react";
import { useLocale } from "@/lib/i18n";
import {
  WORKSPACE_TINTS,
  getWorkspaceTint,
  setWorkspaceTint,
  type WorkspaceTint,
} from "@/lib/tint";
import {
  getActiveWorkspace,
  subscribeWorkspace,
  type Workspace,
} from "@/lib/workspace";

const TINT_SWATCH: Record<WorkspaceTint, string> = {
  default: "#fafaf7",
  green: "#c8e1c4",
  dark: "#cfcfd6",
  orange: "#f1d2a8",
};

const TINT_PREVIEW: Record<WorkspaceTint, string> = {
  default: "var(--surface)",
  green: "linear-gradient(180deg, #f1f6f0, var(--surface))",
  dark: "linear-gradient(180deg, #ececef, var(--surface))",
  orange: "linear-gradient(180deg, #faf3ea, var(--surface))",
};

export function TintSection() {
  const { t } = useLocale();
  const [workspace, setWorkspace] = useState<Workspace>({ kind: "personal" });
  const [tint, setTint] = useState<WorkspaceTint>("default");

  useEffect(() => {
    const compute = () => {
      const w = getActiveWorkspace();
      setWorkspace(w);
      setTint(getWorkspaceTint(w));
    };
    compute();
    return subscribeWorkspace(compute);
  }, []);

  const pick = (next: WorkspaceTint) => {
    setWorkspaceTint(workspace, next);
    setTint(next);
  };

  const scopeLabel =
    workspace.kind === "team"
      ? t("settings.tint.scopeTeam", {
          name: workspace.team_name || workspace.team_id,
        })
      : t("settings.tint.scopePersonal");

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 14,
        }}
      >
        <div>
          <div className="eyebrow">{t("settings.tint.title")}</div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              marginTop: 4,
              lineHeight: 1.5,
            }}
          >
            {t("settings.tint.subtitle")}
          </div>
        </div>
        <div
          style={{
            fontSize: 11,
            color: "var(--text-dim)",
            textAlign: "right",
            maxWidth: 220,
          }}
        >
          {scopeLabel}
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {WORKSPACE_TINTS.map((opt) => {
          const active = tint === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => pick(opt)}
              style={{
                padding: "8px 12px",
                fontSize: 13,
                borderRadius: 10,
                cursor: "pointer",
                border: active
                  ? "1px solid var(--accent)"
                  : "1px solid var(--border)",
                background: TINT_PREVIEW[opt],
                color: active ? "var(--accent)" : "var(--text)",
                fontWeight: active ? 600 : 500,
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: 4,
                  background: TINT_SWATCH[opt],
                  border:
                    "1px solid color-mix(in srgb, black 8%, transparent)",
                }}
              />
              {t(`settings.tint.${opt}` as const)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
