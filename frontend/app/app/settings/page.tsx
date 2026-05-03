"use client";

import { AccountSection } from "@/components/settings/AccountSection";
import { TintSection } from "@/components/settings/TintSection";
import { HelpSection } from "@/components/settings/HelpSection";

export default function SettingsPage() {
  return (
    <>
      <AccountSection />
      <TintSection />
      <HelpSection />
    </>
  );
}
