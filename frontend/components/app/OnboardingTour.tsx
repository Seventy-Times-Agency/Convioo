"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { TourProvider, type StepType, useTour } from "@reactour/tour";
import { completeOnboardingTour } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

const STEP_DEFS = [
  {
    selector: '[data-tour="tour-search"]',
    contentKey: "onboarding.tour.search" as const,
  },
  {
    selector: '[data-tour="tour-search"]',
    contentKey: "onboarding.tour.henry" as const,
  },
  {
    selector: '[data-tour="tour-leads"]',
    contentKey: "onboarding.tour.leads" as const,
  },
  {
    selector: '[data-tour="tour-settings"]',
    contentKey: "onboarding.tour.settings" as const,
  },
];

const TOUR_DISMISSED_KEY = "convioo.tour.dismissed";

export function isTourDismissed(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(TOUR_DISMISSED_KEY) === "1";
}

export function markTourDismissed(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOUR_DISMISSED_KEY, "1");
}

export function clearTourDismissed(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOUR_DISMISSED_KEY);
}

interface ProviderProps {
  children: React.ReactNode;
}

export function OnboardingTourProvider({ children }: ProviderProps) {
  const { t } = useLocale();
  const onClose = useCallback(() => {
    markTourDismissed();
    void completeOnboardingTour().catch(() => undefined);
  }, []);

  const steps = useMemo<StepType[]>(
    () =>
      STEP_DEFS.map((s) => ({
        selector: s.selector,
        content: t(s.contentKey),
      })),
    [t],
  );

  const styles = useMemo(
    () => ({
      popover: (base: React.CSSProperties) => ({
        ...base,
        background: "var(--surface)",
        color: "var(--text)",
        borderRadius: 14,
        border: "1px solid var(--border)",
        boxShadow: "var(--shadow-lg)",
        maxWidth: 360,
        padding: "20px 22px",
        fontSize: 14,
        lineHeight: 1.55,
      }),
      maskArea: (base: React.CSSProperties) => ({ ...base, rx: 10 }),
      badge: (base: React.CSSProperties) => ({
        ...base,
        background: "var(--accent)",
        color: "white",
      }),
      controls: (base: React.CSSProperties) => ({
        ...base,
        marginTop: 16,
      }),
      close: (base: React.CSSProperties) => ({
        ...base,
        color: "var(--text-muted)",
      }),
    }),
    [],
  );

  return (
    <TourProvider
      steps={steps}
      styles={styles}
      onClickClose={({ setIsOpen }) => {
        onClose();
        setIsOpen(false);
      }}
      onClickMask={({ setIsOpen }) => {
        onClose();
        setIsOpen(false);
      }}
      afterOpen={() => undefined}
      beforeClose={() => onClose()}
      showBadge
      disableInteraction
      padding={{ mask: 6, popover: 12 }}
    >
      {children}
    </TourProvider>
  );
}

interface TriggerProps {
  shouldOpen: boolean;
}

/**
 * Mounted inside the TourProvider. Reads the gate prop and opens the
 * tour on first mount when needed. The gate is computed in the parent
 * after auth has resolved so the tour never opens for guests.
 */
export function OnboardingTourTrigger({ shouldOpen }: TriggerProps) {
  const { setIsOpen, isOpen } = useTour();
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!shouldOpen || armed || isOpen) return;
    setArmed(true);
    const id = window.setTimeout(() => setIsOpen(true), 600);
    return () => window.clearTimeout(id);
  }, [shouldOpen, armed, isOpen, setIsOpen]);

  return null;
}

/** Imperative replay button: clears the dismissed flag and opens. */
export function ReplayTourButton({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const { setIsOpen } = useTour();
  return (
    <button
      type="button"
      className={className ?? "btn btn-ghost"}
      onClick={() => {
        clearTourDismissed();
        setIsOpen(true);
      }}
    >
      {children}
    </button>
  );
}
