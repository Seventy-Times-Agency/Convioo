"use client";

import { NotionSection } from "@/components/settings/NotionSection";
import { HubspotSection } from "@/components/settings/HubspotSection";
import { PipedriveSection } from "@/components/settings/PipedriveSection";
import { GmailSection } from "@/components/settings/GmailSection";
import { BackendInfoCards } from "@/components/settings/BackendInfoCards";

export default function SettingsIntegrationsPage() {
  return (
    <>
      <NotionSection />
      <HubspotSection />
      <PipedriveSection />
      <GmailSection />
      <BackendInfoCards />
    </>
  );
}
