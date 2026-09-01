"use client";

import { DeliverabilitySection } from "@/components/settings/DeliverabilitySection";
import { SuppressionsSection } from "@/components/settings/SuppressionsSection";

/** Почта — прогрев, лимиты отправки и список исключений. */
export default function SettingsMailPage() {
  return (
    <>
      <DeliverabilitySection />
      <SuppressionsSection />
    </>
  );
}
