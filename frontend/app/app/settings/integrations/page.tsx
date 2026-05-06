"use client";

import { NotionSection } from "@/components/settings/NotionSection";
import { HubspotSection } from "@/components/settings/HubspotSection";
import { PipedriveSection } from "@/components/settings/PipedriveSection";
import { GmailSection } from "@/components/settings/GmailSection";
import { OutlookSection } from "@/components/settings/OutlookSection";
import { SlackSection } from "@/components/settings/SlackSection";
import { ProxycurlSection } from "@/components/settings/ProxycurlSection";
import { GoogleSheetsSection } from "@/components/settings/GoogleSheetsSection";
import { HunterSection } from "@/components/settings/HunterSection";
import { AdzunaSection } from "@/components/settings/AdzunaSection";
import { CompaniesHouseSection } from "@/components/settings/CompaniesHouseSection";
import { MakeSection } from "@/components/settings/MakeSection";
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
      <GoogleSheetsSection />
      <ProxycurlSection />
      <HunterSection />
      <AdzunaSection />
      <CompaniesHouseSection />
      <MakeSection />
      <BackendInfoCards />
    </>
  );
}
