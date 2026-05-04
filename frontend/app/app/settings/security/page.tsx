"use client";

import { SecuritySection } from "@/components/settings/SecuritySection";
import { ApiKeysSection } from "@/components/settings/ApiKeysSection";
import { AccountDangerZoneSection } from "@/components/settings/AccountDangerZoneSection";

export default function SettingsSecurityPage() {
  return (
    <>
      <SecuritySection />
      <ApiKeysSection />
      <AccountDangerZoneSection />
    </>
  );
}
