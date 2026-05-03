"use client";

import { SecuritySection } from "@/components/settings/SecuritySection";
import { ApiKeysSection } from "@/components/settings/ApiKeysSection";

export default function SettingsSecurityPage() {
  return (
    <>
      <SecuritySection />
      <ApiKeysSection />
    </>
  );
}
