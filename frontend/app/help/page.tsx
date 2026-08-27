"use client";

import { Icon, type IconName } from "@/components/Icon";
import { PublicPageShell } from "@/components/PublicPageShell";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface HelpItem {
  qKey: TranslationKey;
  aKey: TranslationKey;
  icon: IconName;
}

const ITEMS: HelpItem[] = [
  { qKey: "help.q.start", aKey: "help.a.start", icon: "sparkles" },
  { qKey: "help.q.search", aKey: "help.a.search", icon: "search" },
  { qKey: "help.q.import", aKey: "help.a.import", icon: "download" },
  { qKey: "help.q.score", aKey: "help.a.score", icon: "star" },
  { qKey: "help.q.henry", aKey: "help.a.henry", icon: "chat" },
  { qKey: "help.q.team", aKey: "help.a.team", icon: "users" },
  { qKey: "help.q.export", aKey: "help.a.export", icon: "folder" },
  { qKey: "help.q.delete", aKey: "help.a.delete", icon: "x" },
];

export default function HelpPage() {
  const { t } = useLocale();
  return (
    <PublicPageShell width={880}>
      <div style={{ marginBottom: 40 }}>
        <h1
          style={{
            fontSize: 36,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            margin: "0 0 10px",
          }}
        >
          {t("help.title")}
        </h1>
        <div style={{ fontSize: 15, color: "var(--text-muted)" }}>
          {t("help.subtitle")}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {ITEMS.map((item) => (
          <details
            key={item.qKey}
            className="card"
            style={{ padding: 18, cursor: "pointer" }}
          >
            <summary
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                listStyle: "none",
                fontSize: 15,
                fontWeight: 600,
              }}
            >
              <Icon
                name={item.icon}
                size={16}
                style={{ color: "var(--accent)", flexShrink: 0 }}
              />
              <span style={{ flex: 1 }}>{t(item.qKey)}</span>
              <Icon
                name="chevronDown"
                size={14}
                style={{ color: "var(--text-dim)" }}
              />
            </summary>
            <div
              style={{
                marginTop: 12,
                fontSize: 13.5,
                color: "var(--text-muted)",
                lineHeight: 1.7,
              }}
            >
              {t(item.aKey)}
            </div>
          </details>
        ))}
      </div>

      <div
        className="card"
        style={{
          marginTop: 40,
          padding: 22,
          background: "var(--surface-2)",
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
          {t("help.contact.title")}
        </div>
        <div
          style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}
        >
          {t("help.contact.body")}
        </div>
        <a className="btn btn-sm" href="mailto:support@convioo.com">
          <Icon name="mail" size={13} /> support@convioo.com
        </a>
      </div>
    </PublicPageShell>
  );
}
