"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import { useTheme } from "@/components/ThemeProvider";

interface Shortcut {
  combo: string;
  labelKey: TranslationKey;
  run: (router: ReturnType<typeof useRouter>, theme: ReturnType<typeof useTheme>) => void;
}

const SHORTCUTS: Shortcut[] = [
  {
    combo: "g d",
    labelKey: "kbd.dashboard",
    run: (r) => r.push("/app"),
  },
  {
    combo: "g s",
    labelKey: "kbd.search",
    run: (r) => r.push("/app/search"),
  },
  {
    combo: "g l",
    labelKey: "kbd.leads",
    run: (r) => r.push("/app/leads"),
  },
  {
    combo: "g i",
    labelKey: "kbd.import",
    run: (r) => r.push("/app/import"),
  },
  {
    combo: "g t",
    labelKey: "kbd.templates",
    run: (r) => r.push("/app/templates"),
  },
  {
    combo: "g p",
    labelKey: "kbd.profile",
    run: (r) => r.push("/app/profile"),
  },
  {
    combo: "t",
    labelKey: "kbd.theme",
    run: (_r, theme) => theme.toggle(),
  },
];

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return false;
}

/**
 * Mounts once at app layout level. Listens for keypresses, supports
 * "g d" style chord shortcuts (press g then d within 1.5s), pure
 * single-key shortcuts and "?" to show the cheat-sheet overlay.
 *
 * Skipped while the user is typing in an input so it doesn't fight
 * the search field or note editor.
 */
export function KeyboardShortcuts() {
  const router = useRouter();
  const theme = useTheme();
  const { t } = useLocale();
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    let lead: string | null = null;
    let leadAt = 0;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;

      if (e.key === "?") {
        e.preventDefault();
        setShowHelp((v) => !v);
        return;
      }
      if (e.key === "Escape" && showHelp) {
        setShowHelp(false);
        return;
      }

      const now = Date.now();
      const k = e.key.toLowerCase();

      // Single-key shortcuts (e.g. "t" to toggle theme).
      const single = SHORTCUTS.find((s) => s.combo === k);
      if (single && lead === null) {
        e.preventDefault();
        single.run(router, theme);
        return;
      }

      // Chord shortcuts: first press the lead key, then the second
      // letter within 1.5s.
      if (lead === null && k === "g") {
        lead = "g";
        leadAt = now;
        return;
      }
      if (lead && now - leadAt < 1500) {
        const combo = `${lead} ${k}`;
        const sc = SHORTCUTS.find((s) => s.combo === combo);
        if (sc) {
          e.preventDefault();
          sc.run(router, theme);
        }
        lead = null;
        return;
      }
      lead = null;
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [router, theme, showHelp]);

  if (!showHelp) return null;
  return (
    <div className="kbd-overlay-bg" onClick={() => setShowHelp(false)}>
      <div className="kbd-overlay" onClick={(e) => e.stopPropagation()}>
        <div
          style={{
            fontSize: 16,
            fontWeight: 700,
            marginBottom: 12,
            letterSpacing: "-0.01em",
          }}
        >
          {t("kbd.title")}
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          {SHORTCUTS.map((s) => (
            <div key={s.combo} className="kbd-row">
              <div className="label">{t(s.labelKey)}</div>
              <div>
                {s.combo.split(" ").map((piece, i) => (
                  <span key={i} className="kbd-key">
                    {piece}
                  </span>
                ))}
              </div>
            </div>
          ))}
          <div className="kbd-row">
            <div className="label">{t("kbd.toggleHelp")}</div>
            <div>
              <span className="kbd-key">?</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
