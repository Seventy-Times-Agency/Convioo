"use client";

import Link from "next/link";
import { Icon } from "@/components/brand/Icon";
import { useLocale } from "@/lib/i18n";

/** Переключатель режима работы селза: прозвон ↔ письма. Один и тот
 * же в шапке обеих страниц, чтобы прыгать между ними не думая. */
export function WorkModeSwitch({ mode }: { mode: "calls" | "letters" }) {
  const { t } = useLocale();
  const items: { key: "calls" | "letters"; href: string; icon: "phone" | "mail"; label: string }[] = [
    { key: "calls", href: "/app/work", icon: "phone", label: t("letters.tabCalls") },
    { key: "letters", href: "/app/work/letters", icon: "mail", label: t("letters.tabLetters") },
  ];
  return (
    <div className="seg" style={{ padding: 2 }}>
      {items.map((it) => (
        <Link
          key={it.key}
          href={it.href}
          className={mode === it.key ? "active" : ""}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 11px",
            fontSize: 12.5,
            fontWeight: 600,
            borderRadius: 6,
            color: mode === it.key ? "var(--text)" : "var(--text-muted)",
            background: mode === it.key ? "var(--surface)" : "transparent",
            boxShadow: mode === it.key ? "var(--shadow-sm)" : "none",
            textDecoration: "none",
          }}
        >
          <Icon name={it.icon} size={12} />
          {it.label}
        </Link>
      ))}
    </div>
  );
}
