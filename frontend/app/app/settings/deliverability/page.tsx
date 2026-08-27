"use client";

import { DeliverabilitySection } from "@/components/settings/DeliverabilitySection";
import { SuppressionsSection } from "@/components/settings/SuppressionsSection";

export default function SettingsDeliverabilityPage() {
  return (
    <>
      <DeliverabilitySection />
      <SuppressionsSection />
    </>
  );
}
