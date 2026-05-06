"use client";

import { NotionSection } from "@/components/settings/NotionSection";
import { HubspotSection } from "@/components/settings/HubspotSection";
import { PipedriveSection } from "@/components/settings/PipedriveSection";
import { GmailSection } from "@/components/settings/GmailSection";
import { OutlookSection } from "@/components/settings/OutlookSection";
import { SlackSection } from "@/components/settings/SlackSection";
import { ProxycurlSection } from "@/components/settings/ProxycurlSection";
import { BackendInfoCards } from "@/components/settings/BackendInfoCards";

export default function SettingsIntegrationsPage() {
  return (
    <>
      <GmailSection />
      <OutlookSection />
      <NotionSection />
      <HubspotSection />
      <PipedriveSection />
      <SlackSection />
      <ProxycurlSection />
      <BackendInfoCards />
    </>
  );
}
