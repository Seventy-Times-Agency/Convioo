"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Icon, type IconName } from "@/components/Icon";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import {
  type BillingSubscription,
  getBillingSubscription,
  openBillingPortal,
  startBillingCheckout,
} from "@/lib/api";

/**
 * Subscription plans surface.
 *
 * Cards mirror the four-tier ladder. Real Stripe checkout drives the
 * paid CTAs — when the backend returns 503 (no STRIPE_SECRET_KEY) we
 * surface a friendly hint instead of crashing. Active customers see
 * a "Manage subscription" button that pops the Stripe Customer Portal.
 */

interface PlanFeature {
  labelKey: TranslationKey;
  /** Whether this feature is included on the plan. ``false`` ones
   *  render greyed-out so the user can compare quickly. */
  included: boolean;
}

interface Plan {
  id: "free" | "personal_pro" | "team_standard" | "team_pro";
  highlight?: boolean;
  icon: IconName;
  accent: string;
  /** Backend slug (`pro` / `agency`) — `null` means the card is not
   *  buyable today (free tier or staff-only enterprise tier). */
  stripePlan: "pro" | "agency" | null;
}

const PLANS: Plan[] = [
  { id: "free", icon: "sparkles", accent: "var(--text-muted)", stripePlan: null },
  {
    id: "personal_pro",
    icon: "zap",
    accent: "var(--accent)",
    highlight: true,
    stripePlan: "pro",
  },
  { id: "team_standard", icon: "users", accent: "#16A34A", stripePlan: "agency" },
  { id: "team_pro", icon: "star", accent: "#EA580C", stripePlan: "agency" },
];

const FEATURES: Record<Plan["id"], PlanFeature[]> = {
  free: [
    { labelKey: "billing.feat.searchesFree", included: true },
    { labelKey: "billing.feat.leadsPerSession", included: true },
    { labelKey: "billing.feat.aiScore", included: true },
    { labelKey: "billing.feat.henryConsult", included: true },
    { labelKey: "billing.feat.crmBasic", included: true },
    { labelKey: "billing.feat.exportCsv", included: false },
    { labelKey: "billing.feat.dailyDigest", included: false },
    { labelKey: "billing.feat.teams", included: false },
    { labelKey: "billing.feat.customFields", included: false },
    { labelKey: "billing.feat.apiAccess", included: false },
  ],
  personal_pro: [
    { labelKey: "billing.feat.searchesPro", included: true },
    { labelKey: "billing.feat.leadsPerSession", included: true },
    { labelKey: "billing.feat.aiScore", included: true },
    { labelKey: "billing.feat.henryConsult", included: true },
    { labelKey: "billing.feat.crmBasic", included: true },
    { labelKey: "billing.feat.exportCsv", included: true },
    { labelKey: "billing.feat.dailyDigest", included: true },
    { labelKey: "billing.feat.outreachTemplates", included: true },
    { labelKey: "billing.feat.unlimitedHistory", included: true },
    { labelKey: "billing.feat.teams", included: false },
  ],
  team_standard: [
    { labelKey: "billing.feat.team5", included: true },
    { labelKey: "billing.feat.searchesTeamStandard", included: true },
    { labelKey: "billing.feat.sharedCrm", included: true },
    { labelKey: "billing.feat.dedupTeam", included: true },
    { labelKey: "billing.feat.henryTeam", included: true },
    { labelKey: "billing.feat.activityFeed", included: true },
    { labelKey: "billing.feat.weeklyCheckin", included: true },
    { labelKey: "billing.feat.exportCsv", included: true },
    { labelKey: "billing.feat.customFields", included: false },
    { labelKey: "billing.feat.apiAccess", included: false },
  ],
  team_pro: [
    { labelKey: "billing.feat.team25", included: true },
    { labelKey: "billing.feat.searchesTeamPro", included: true },
    { labelKey: "billing.feat.sharedCrm", included: true },
    { labelKey: "billing.feat.dedupTeam", included: true },
    { labelKey: "billing.feat.henryTeam", included: true },
    { labelKey: "billing.feat.activityFeed", included: true },
    { labelKey: "billing.feat.weeklyCheckin", included: true },
    { labelKey: "billing.feat.kanbanPipeline", included: true },
    { labelKey: "billing.feat.customFields", included: true },
    { labelKey: "billing.feat.searchAlerts", included: true },
    { labelKey: "billing.feat.apiAccess", included: true },
    { labelKey: "billing.feat.prioritySupport", included: true },
  ],
};

export default function BillingPage() {
  const { t } = useLocale();
  const [sub, setSub] = useState<BillingSubscription | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Plan["id"] | "portal" | null>(null);

  useEffect(() => {
    let cancelled = false;
    getBillingSubscription()
      .then((s) => {
        if (!cancelled) setSub(s);
      })
      .catch(() => {
        // Ignore: card just renders without status badge.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubscribe(plan: Plan) {
    if (!plan.stripePlan) return;
    setError(null);
    setPending(plan.id);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const { url } = await startBillingCheckout({
        plan: plan.stripePlan,
        successUrl: `${origin}/app/billing?status=success`,
        cancelUrl: `${origin}/app/billing?status=cancel`,
      });
      window.location.href = url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Stripe error";
      setError(msg);
    } finally {
      setPending(null);
    }
  }

  async function onManage() {
    setError(null);
    setPending("portal");
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      const { url } = await openBillingPortal(`${origin}/app/billing`);
      window.location.href = url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Stripe error";
      setError(msg);
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <Topbar
        title={t("billing.title")}
        subtitle={t("billing.subtitle")}
        right={
          sub && (sub.paid_active || sub.trial_active) ? (
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                padding: "4px 10px",
                borderRadius: 999,
                background:
                  "color-mix(in srgb, var(--accent) 14%, var(--surface))",
                color: "var(--accent)",
                border:
                  "1px solid color-mix(in srgb, var(--accent) 40%, var(--border))",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              {sub.paid_active ? sub.plan : "trial"}
            </span>
          ) : null
        }
      />
      <div className="page" style={{ maxWidth: 1240 }}>
        {sub && (sub.trial_active || sub.paid_active) && (
          <div
            style={{
              padding: "16px 20px",
              borderRadius: 12,
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              marginBottom: 16,
              fontSize: 13.5,
              color: "var(--text)",
              lineHeight: 1.55,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
              flexWrap: "wrap",
            }}
          >
            <div>
              {sub.paid_active && sub.plan_until && (
                <>
                  <strong>{sub.plan.toUpperCase()}</strong> — активна до{" "}
                  {new Date(sub.plan_until).toLocaleDateString()}
                </>
              )}
              {!sub.paid_active && sub.trial_active && sub.trial_ends_at && (
                <>
                  Триал до {new Date(sub.trial_ends_at).toLocaleDateString()}.
                  Оформите план, чтобы не потерять доступ.
                </>
              )}
            </div>
            {sub.has_stripe_customer && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={onManage}
                disabled={pending === "portal"}
              >
                {pending === "portal" ? "..." : "Управление"}
              </button>
            )}
          </div>
        )}

        {error && (
          <div
            style={{
              padding: "12px 16px",
              borderRadius: 10,
              background:
                "color-mix(in srgb, var(--cold) 12%, var(--surface))",
              border:
                "1px solid color-mix(in srgb, var(--cold) 40%, var(--border))",
              marginBottom: 16,
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 16,
          }}
        >
          {PLANS.map((p) => {
            const features = FEATURES[p.id];
            return (
              <PlanCard
                key={p.id}
                plan={p}
                features={features}
                onSubscribe={() => onSubscribe(p)}
                pending={pending === p.id}
                currentPlan={sub?.plan ?? null}
              />
            );
          })}
        </div>

        <div
          className="card"
          style={{ padding: 20, marginTop: 24 }}
        >
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            {t("billing.teamGate.title")}
          </div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.55,
            }}
          >
            {t("billing.teamGate.body")}
          </div>
        </div>
      </div>
    </>
  );
}

function PlanCard({
  plan,
  features,
  onSubscribe,
  pending,
  currentPlan,
}: {
  plan: Plan;
  features: PlanFeature[];
  onSubscribe: () => void;
  pending: boolean;
  currentPlan: string | null;
}) {
  const { t } = useLocale();
  const id = plan.id;
  const isCurrent =
    currentPlan && plan.stripePlan && currentPlan === plan.stripePlan;
  return (
    <div
      className="card"
      style={{
        padding: "22px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 14,
        borderColor: plan.highlight
          ? "color-mix(in srgb, var(--accent) 50%, var(--border))"
          : undefined,
        boxShadow: plan.highlight
          ? "0 8px 24px color-mix(in srgb, var(--accent) 18%, transparent)"
          : undefined,
        background: plan.highlight
          ? "linear-gradient(180deg, color-mix(in srgb, var(--accent) 5%, var(--surface)), var(--surface))"
          : undefined,
        position: "relative",
      }}
    >
      {plan.highlight && (
        <span
          style={{
            position: "absolute",
            top: -10,
            right: 16,
            fontSize: 10,
            fontWeight: 700,
            padding: "3px 9px",
            borderRadius: 999,
            background: "var(--accent)",
            color: "white",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {t("billing.popular")}
        </span>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: `color-mix(in srgb, ${plan.accent} 14%, var(--surface))`,
            color: plan.accent,
            display: "grid",
            placeItems: "center",
            flexShrink: 0,
          }}
        >
          <Icon name={plan.icon} size={16} />
        </div>
        <div
          style={{
            fontSize: 16,
            fontWeight: 700,
            letterSpacing: "-0.01em",
          }}
        >
          {t(`billing.plan.${id}.name` as TranslationKey)}
        </div>
      </div>

      <div
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          minHeight: 38,
        }}
      >
        {t(`billing.plan.${id}.tagline` as TranslationKey)}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 6,
          padding: "10px 12px",
          borderRadius: 10,
          background: "var(--surface-2)",
        }}
      >
        <span
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.02em",
          }}
        >
          {t(`billing.plan.${id}.price` as TranslationKey)}
        </span>
        <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {t(`billing.plan.${id}.period` as TranslationKey)}
        </span>
      </div>

      <button
        type="button"
        className="btn btn-sm"
        disabled={!plan.stripePlan || pending || Boolean(isCurrent)}
        onClick={() => {
          if (plan.stripePlan && !isCurrent) onSubscribe();
        }}
        style={{
          opacity: plan.stripePlan && !isCurrent ? 1 : 0.55,
          cursor: plan.stripePlan && !isCurrent ? "pointer" : "not-allowed",
          justifyContent: "center",
        }}
      >
        {pending
          ? "..."
          : isCurrent
            ? "Текущий план"
            : plan.stripePlan
              ? "Подключить"
              : t("billing.cta")}
      </button>

      <div
        style={{
          height: 1,
          background: "var(--border)",
          margin: "4px 0 0",
        }}
      />

      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {features.map((f) => (
          <li
            key={f.labelKey}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 8,
              fontSize: 12.5,
              color: f.included ? "var(--text)" : "var(--text-dim)",
              opacity: f.included ? 1 : 0.55,
              lineHeight: 1.45,
            }}
          >
            <Icon
              name={f.included ? "check" : "x"}
              size={12}
              style={{
                color: f.included ? "var(--hot)" : "var(--text-dim)",
                marginTop: 2,
                flexShrink: 0,
              }}
            />
            <span>{t(f.labelKey)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
