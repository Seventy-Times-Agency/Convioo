"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Icon } from "@/components/brand/Icon";
import {
  getNotifications,
  getUnreadNotifications,
  markNotificationsRead,
  type AppNotification,
  type NotificationCounts,
} from "@/lib/api";
import { useLocale, type TranslationKey } from "@/lib/i18n";

const POLL_MS = 30_000;

/** Значок и действие по типу события. */
const KIND: Record<string, { mark: string; tone: string; action?: TranslationKey }> = {
  hot_reply: { mark: "↩", tone: "hot", action: "ntf.act.reply" },
  overdue: { mark: "!", tone: "bad", action: "ntf.act.call" },
  escalation: { mark: "!", tone: "bad", action: "ntf.act.open" },
  batch: { mark: "+", tone: "info", action: "ntf.act.queue" },
  goal: { mark: "✓", tone: "goal" },
  letter_waiting: { mark: "✉", tone: "warn", action: "ntf.act.open" },
  search_done: { mark: "⌕", tone: "info", action: "ntf.act.open" },
  budget: { mark: "$", tone: "warn", action: "ntf.act.open" },
  digest: { mark: "≡", tone: "info" },
};

/** Колокольчик в левой панели: счётчик непрочитанного и окно с
 * вкладками «Важное» / «Все». Клик по уведомлению ведёт к делу. */
export function NotificationBell({ onNavigate }: { onNavigate?: () => void }) {
  const { t, lang } = useLocale();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"important" | "all">("important");
  const [counts, setCounts] = useState<NotificationCounts>({ unread: 0, unread_important: 0 });
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [seen, setSeen] = useState<Set<string>>(() => new Set());
  const boxRef = useRef<HTMLDivElement>(null);

  const refreshCounts = useCallback(() => {
    getUnreadNotifications().then(setCounts).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshCounts();
    const id = window.setInterval(refreshCounts, POLL_MS);
    const onFocus = () => refreshCounts();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [refreshCounts]);

  // Лента грузится при открытии и при смене вкладки.
  useEffect(() => {
    if (!open) return;
    let stale = false;
    getNotifications(tab === "important")
      .then((feed) => {
        if (stale) return;
        setItems(feed.items);
        setCounts({ unread: feed.unread, unread_important: feed.unread_important });
      })
      .catch(() => !stale && setItems([]));
    return () => {
      stale = true;
    };
  }, [open, tab]);

  // Закрытие по клику мимо и по Esc.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = () => {
    setOpen((v) => {
      if (!v) {
        setItems(null);
        // Важного нет — сразу показываем всё, а не пустую вкладку.
        setTab(counts.unread_important > 0 || counts.unread === 0 ? "important" : "all");
      } else if (items) {
        setSeen(new Set(items.map((n) => n.id)));
      }
      return !v;
    });
  };

  const openItem = async (n: AppNotification) => {
    if (!n.read) {
      markNotificationsRead({ ids: [n.id] }).then(setCounts).catch(() => undefined);
    }
    setOpen(false);
    onNavigate?.();
    if (n.link) router.push(n.link);
  };

  const readAll = async () => {
    try {
      setCounts(await markNotificationsRead({ all: true }));
      setItems((list) => list?.map((n) => ({ ...n, read: true })) ?? list);
    } catch {
      // badge just stays as is
    }
  };

  const ago = (iso: string): string => {
    const diff = Math.max(0, Date.now() - new Date(iso).getTime());
    const min = Math.round(diff / 60_000);
    if (min < 1) return t("ntf.now");
    if (min < 60) return t("ntf.min", { n: min });
    const h = Math.round(min / 60);
    if (h < 24) return t("ntf.hour", { n: h });
    return new Date(iso).toLocaleDateString(
      lang === "en" ? "en-US" : lang === "uk" ? "uk-UA" : "ru-RU",
      { day: "numeric", month: "short" },
    );
  };

  const badge = counts.unread > 99 ? "99+" : String(counts.unread);

  return (
    <div className="ntf" ref={boxRef}>
      <button
        type="button"
        className={"rail-ghost ntf-bell" + (open ? " open" : "")}
        onClick={toggle}
        title={t("ntf.title")}
        aria-label={t("ntf.title")}
        aria-expanded={open}
      >
        <Icon name="bell" size={18} />
        {counts.unread > 0 && (
          <span key={counts.unread} className="ntf-badge m-pop">
            {badge}
          </span>
        )}
      </button>

      {open && (
        <div className="ntf-pop anim-pop" role="dialog" aria-label={t("ntf.title")}>
          <div className="ntf-head">
            <b>{t("ntf.title")}</b>
            <div className="seg" style={{ padding: 2 }}>
              <button
                type="button"
                className={tab === "important" ? "active" : ""}
                onClick={() => setTab("important")}
                style={{ padding: "4px 9px", fontSize: 11.5 }}
              >
                {t("ntf.important")}
                {counts.unread_important > 0 ? ` · ${counts.unread_important}` : ""}
              </button>
              <button
                type="button"
                className={tab === "all" ? "active" : ""}
                onClick={() => setTab("all")}
                style={{ padding: "4px 9px", fontSize: 11.5 }}
              >
                {t("ntf.all")}
              </button>
            </div>
          </div>

          <div className="ntf-list">
            {items === null && <div className="ntf-empty">{t("common.loading")}</div>}
            {items?.length === 0 && (
              <div className="ntf-empty">
                {tab === "important" ? t("ntf.emptyImportant") : t("ntf.empty")}
              </div>
            )}
            {items?.map((n) => {
              const k = KIND[n.kind] ?? KIND.digest;
              return (
                <button
                  key={n.id}
                  type="button"
                  className={
                    "ntf-item" +
                    (n.read ? "" : " unread") +
                    (!n.read && !seen.has(n.id) ? " m-arrive" : "")
                  }
                  onClick={() => void openItem(n)}
                >
                  <span className={"ntf-ic " + k.tone}>{k.mark}</span>
                  <span className="ntf-text">
                    <span className="ntf-t">{n.title}</span>
                    {n.body && <span className="ntf-d">{n.body}</span>}
                    <span className="ntf-m">
                      {ago(n.created_at)}
                      {k.action && n.link && <span className="ntf-act">{t(k.action)}</span>}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          <div className="ntf-foot">
            <button type="button" onClick={() => void readAll()} disabled={counts.unread === 0}>
              {t("ntf.readAll")}
            </button>
            <button
              type="button"
              className="ntf-link"
              onClick={() => {
                setOpen(false);
                onNavigate?.();
                router.push("/app/profile");
              }}
            >
              {t("ntf.settings")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
