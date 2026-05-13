"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useLocale } from "@/lib/i18n";
import { getBillingSubscription } from "@/lib/api/billing";

/**
 * Show a banner at the top of /app/* when the user's trial has 3 or
 * fewer days left. Hidden once the user upgrades (paid_active) or
 * once the trial has expired (server-side billing then surfaces a
 * different state).
 */
export function TrialBanner() {
  const { t } = useLocale();
  const [daysLeft, setDaysLeft] = useState<number | null>(null);
  const [variant, setVariant] = useState<"warn" | "danger">("warn");

  useEffect(() => {
    let cancelled = false;
    getBillingSubscription()
      .then((sub) => {
        if (cancelled) return;
        if (sub.paid_active) return;
        if (!sub.trial_active || !sub.trial_ends_at) return;
        const endsAt = new Date(sub.trial_ends_at).getTime();
        const now = Date.now();
        const days = Math.ceil((endsAt - now) / (24 * 60 * 60 * 1000));
        if (days > 3 || days < 0) return;
        setDaysLeft(days);
        setVariant(days <= 1 ? "danger" : "warn");
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (daysLeft === null) return null;

  const bg = variant === "danger" ? "#fee2e2" : "#fef9c3";
  const fg = variant === "danger" ? "#7f1d1d" : "#713f12";
  const border = variant === "danger" ? "#f87171" : "#facc15";

  return (
    <div
      role="status"
      style={{
        background: bg,
        color: fg,
        borderBottom: `1px solid ${border}`,
        padding: "10px 16px",
        fontSize: 13,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
      }}
    >
      <span>
        {daysLeft === 0
          ? t("billing.trial.endsToday")
          : t("billing.trial.endsIn", { days: daysLeft })}
      </span>
      <Link
        href="/pricing"
        style={{
          color: fg,
          textDecoration: "underline",
          fontWeight: 600,
        }}
      >
        {t("billing.trial.upgradeCta")}
      </Link>
    </div>
  );
}
