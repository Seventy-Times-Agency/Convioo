"use client";

import { AccountSection } from "@/components/settings/AccountSection";
import { HelpSection } from "@/components/settings/HelpSection";
import { LanguageSection } from "@/components/settings/LanguageSection";

export default function SettingsPage() {
  return (
    <>
      <AccountSection />
      <LanguageSection />
      <HelpSection />
    </>
  );
}
