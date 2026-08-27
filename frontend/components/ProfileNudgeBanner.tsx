"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { getMyProfile, type UserProfile } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

const DISMISS_KEY = "convioo.profile.nudge.dismissedOn";

function isProfileFilledEnough(profile: UserProfile): boolean {
  // The two fields AI leans on hardest for personalisation. Niches +
  // home_region are nice-to-haves; the nudge nags until the offer is
  // present, then becomes content with a half-filled profile.
  return Boolean(
    profile.service_description?.trim() && profile.profession?.trim(),
  );
}

function dismissedToday(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(DISMISS_KEY);
  if (!raw) return false;
  const today = new Date().toISOString().slice(0, 10);
  return raw === today;
}

/**
 * Soft nudge shown on /app pages when the profile is missing the
 * fields that drive AI score quality. Two CTAs: jump to the manual
 * editor on /app/profile, or pop the floating Henry widget so the
 * user can fill it conversationally. Dismiss-for-today keeps the
 * banner from being annoying after the user explicitly says "later".
 */
export function ProfileNudgeBanner() {
  const { t } = useLocale();
  const [show, setShow] = useState(false);

  useEffect(() => {
    const u = getCurrentUser();
    if (!u) return;
    if (dismissedToday()) return;
    let cancelled = false;
    getMyProfile(u.user_id)
      .then((profile) => {
        if (cancelled) return;
        if (!isProfileFilledEnough(profile)) {
          setShow(true);
        }
      })
      .catch(() => {
        // Silent — we'd rather not nag than show on top of an error.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!show) return null;

  const dismiss = () => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        DISMISS_KEY,
        new Date().toISOString().slice(0, 10),
      );
    }
    setShow(false);
  };

  const askHenry = () => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(new CustomEvent("convioo:open-henry"));
  };

  return (
    <div
      style={{
        margin: "16px 24px 0",
        padding: "16px 18px",
        borderRadius: 12,
        background:
          "linear-gradient(135deg, color-mix(in srgb, var(--accent) 10%, var(--surface)), var(--surface))",
        border:
          "1px solid color-mix(in srgb, var(--accent) 28%, var(--border))",
        display: "flex",
        alignItems: "flex-start",
        gap: 14,
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 10,
          background: "color-mix(in srgb, var(--accent) 16%, var(--surface))",
          display: "grid",
          placeItems: "center",
          color: "var(--accent)",
          flexShrink: 0,
        }}
      >
        <Icon name="sparkles" size={18} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: "-0.005em",
            marginBottom: 4,
          }}
        >
          {t("profile.nudge.title")}
        </div>
        <div
          style={{
            fontSize: 13,
            color: "var(--text-muted)",
            lineHeight: 1.55,
            marginBottom: 12,
          }}
        >
          {t("profile.nudge.body")}
        </div>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignItems: "center",
          }}
        >
          <Link href="/app/profile" className="btn btn-sm">
            <Icon name="pencil" size={13} />
            {t("profile.nudge.manual")}
          </Link>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={askHenry}
          >
            <Icon name="sparkles" size={13} />
            {t("profile.nudge.henry")}
          </button>
          <button
            type="button"
            onClick={dismiss}
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "none",
              color: "var(--text-dim)",
              fontSize: 12,
              cursor: "pointer",
              padding: "4px 6px",
            }}
          >
            {t("profile.nudge.dismiss")}
          </button>
        </div>
      </div>
    </div>
  );
}
