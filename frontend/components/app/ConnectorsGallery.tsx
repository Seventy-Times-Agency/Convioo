"use client";

import { useEffect, useState, type ComponentType } from "react";
import { Icon } from "@/components/Icon";
import { LogoTile } from "@/components/app/connectorLogos";
import { useLocale, type TranslationKey } from "@/lib/i18n";
import {
  getGmailStatus,
  getOutlookStatus,
  getNotionStatus,
  getHubspotStatus,
  getPipedriveStatus,
} from "@/lib/api";

import { GmailSection } from "@/components/settings/GmailSection";
import { OutlookSection } from "@/components/settings/OutlookSection";
import { NotionSection } from "@/components/settings/NotionSection";
import { HubspotSection } from "@/components/settings/HubspotSection";
import { PipedriveSection } from "@/components/settings/PipedriveSection";
import { SlackSection } from "@/components/settings/SlackSection";
import { GoogleSheetsSection } from "@/components/settings/GoogleSheetsSection";
import { ProxycurlSection } from "@/components/settings/ProxycurlSection";
import { HunterSection } from "@/components/settings/HunterSection";
import { AdzunaSection } from "@/components/settings/AdzunaSection";
import { CompaniesHouseSection } from "@/components/settings/CompaniesHouseSection";
import { MakeSection } from "@/components/settings/MakeSection";

/**
 * Connectors marketplace — a logo gallery of every integration, grouped
 * by category. Clicking a tile opens a modal containing that connector's
 * existing settings Section (OAuth button / key fields), so all the
 * connect/disconnect logic is reused verbatim; this file only changes how
 * connectors are presented (gallery + on-demand card) instead of one long
 * stacked Settings page.
 */

type CategoryKey =
  | "email"
  | "crm"
  | "export"
  | "enrichment"
  | "sources"
  | "automation";

interface Connector {
  id: string;
  name: string;
  desc: string;
  category: CategoryKey;
  /** brand colour for the monogram tile */
  color: string;
  /** 1-2 char monogram shown on the tile (avoids shipping trademarked SVGs) */
  mark: string;
  Section: ComponentType;
  /** optional status probe for the "Connected" badge on the tile */
  status?: () => Promise<boolean>;
}

const CATEGORIES: { key: CategoryKey; label: TranslationKey }[] = [
  { key: "email", label: "connectors.cat.email" },
  { key: "crm", label: "connectors.cat.crm" },
  { key: "export", label: "connectors.cat.export" },
  { key: "enrichment", label: "connectors.cat.enrichment" },
  { key: "sources", label: "connectors.cat.sources" },
  { key: "automation", label: "connectors.cat.automation" },
];

const CONNECTORS: Connector[] = [
  {
    id: "gmail",
    name: "Gmail",
    desc: "Send outreach from your Google Workspace inbox.",
    category: "email",
    color: "#EA4335",
    mark: "Gm",
    Section: GmailSection,
    status: () => getGmailStatus().then((s) => s.connected),
  },
  {
    id: "outlook",
    name: "Outlook",
    desc: "Send outreach from your Microsoft 365 inbox.",
    category: "email",
    color: "#0F6CBD",
    mark: "Ol",
    Section: OutlookSection,
    status: () => getOutlookStatus().then((s) => s.connected),
  },
  {
    id: "hubspot",
    name: "HubSpot",
    desc: "Push qualified leads into your HubSpot CRM.",
    category: "crm",
    color: "#FF7A59",
    mark: "Hs",
    Section: HubspotSection,
    status: () => getHubspotStatus().then((s) => s.connected),
  },
  {
    id: "pipedrive",
    name: "Pipedrive",
    desc: "Push qualified leads into your Pipedrive CRM.",
    category: "crm",
    color: "#1F7A3D",
    mark: "Pd",
    Section: PipedriveSection,
    status: () => getPipedriveStatus().then((s) => s.connected),
  },
  {
    id: "notion",
    name: "Notion",
    desc: "Two-way sync of leads with a Notion database.",
    category: "export",
    color: "#111111",
    mark: "No",
    Section: NotionSection,
    status: () => getNotionStatus().then((s) => s.connected),
  },
  {
    id: "sheets",
    name: "Google Sheets",
    desc: "Export search results straight into a spreadsheet.",
    category: "export",
    color: "#0F9D58",
    mark: "Sh",
    Section: GoogleSheetsSection,
  },
  {
    id: "hunter",
    name: "Hunter",
    desc: "Find and verify business email addresses.",
    category: "enrichment",
    color: "#FB6E52",
    mark: "Hn",
    Section: HunterSection,
  },
  {
    id: "proxycurl",
    name: "Proxycurl",
    desc: "Enrich leads with decision-maker LinkedIn data.",
    category: "enrichment",
    color: "#5B4FE0",
    mark: "Px",
    Section: ProxycurlSection,
  },
  {
    id: "adzuna",
    name: "Adzuna",
    desc: "Find companies that are actively hiring.",
    category: "sources",
    color: "#7B2D8E",
    mark: "Az",
    Section: AdzunaSection,
  },
  {
    id: "companies_house",
    name: "Companies House",
    desc: "Surface newly registered UK businesses.",
    category: "sources",
    color: "#1D70B8",
    mark: "CH",
    Section: CompaniesHouseSection,
  },
  {
    id: "make",
    name: "Make",
    desc: "Automate workflows with Make scenarios.",
    category: "automation",
    color: "#6D00CC",
    mark: "Mk",
    Section: MakeSection,
  },
  {
    id: "slack",
    name: "Slack",
    desc: "Get new-lead and reply alerts in a Slack channel.",
    category: "automation",
    color: "#4A154B",
    mark: "Sl",
    Section: SlackSection,
  },
];

export function ConnectorsGallery() {
  const { t } = useLocale();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<Connector | null>(null);
  const [connected, setConnected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled(
      CONNECTORS.filter((c) => c.status).map(async (c) => {
        const ok = await c.status!();
        return [c.id, ok] as const;
      }),
    ).then((results) => {
      if (cancelled) return;
      const next: Record<string, boolean> = {};
      for (const r of results) {
        if (r.status === "fulfilled") next[r.value[0]] = r.value[1];
      }
      setConnected(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const q = query.trim().toLowerCase();
  const visible = q
    ? CONNECTORS.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.desc.toLowerCase().includes(q),
      )
    : CONNECTORS;

  const connectedCount = Object.values(connected).filter(Boolean).length;

  return (
    <>
      {/* Hero — one clear intro + the total connected count. */}
      <div
        className="glass"
        style={{
          borderRadius: 18,
          padding: "22px 24px",
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 20,
          flexWrap: "wrap",
        }}
      >
        <div style={{ maxWidth: 560 }}>
          <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.02em", marginBottom: 6 }}>
            {t("connectors.heroTitle")}
          </div>
          <div style={{ fontSize: 13.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
            {t("connectors.heroBody")}
          </div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div className="gradient-text" style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em" }}>
            {connectedCount}
            <span style={{ color: "var(--text-dim)", fontWeight: 600 }}>/{CONNECTORS.length}</span>
          </div>
          <div className="eyebrow" style={{ marginTop: 2 }}>
            {t("connectors.connected")}
          </div>
        </div>
      </div>

      <div style={{ marginBottom: 20, maxWidth: 360 }}>
        <input
          className="input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("connectors.searchPlaceholder")}
          aria-label={t("connectors.searchPlaceholder")}
          style={{ width: "100%" }}
        />
      </div>

      {CATEGORIES.map((cat) => {
        const items = visible.filter((c) => c.category === cat.key);
        if (items.length === 0) return null;
        return (
          <div key={cat.key} style={{ marginBottom: 26 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 12,
              }}
            >
              <span className="eyebrow">{t(cat.label)}</span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: "var(--text-dim)",
                }}
              >
                {items.length}
              </span>
            </div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 12,
              }}
            >
              {items.map((c) => (
                <ConnectorCard
                  key={c.id}
                  connector={c}
                  connected={connected[c.id]}
                  onOpen={() => setActive(c)}
                />
              ))}
            </div>
          </div>
        );
      })}

      {visible.length === 0 && (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          {t("connectors.noResults")}
        </div>
      )}

      {active && (
        <ConnectorModal connector={active} onClose={() => setActive(null)} />
      )}
    </>
  );
}

function ConnectorCard({
  connector,
  connected,
  onOpen,
}: {
  connector: Connector;
  connected: boolean | undefined;
  onOpen: () => void;
}) {
  const { t } = useLocale();
  return (
    <button
      type="button"
      onClick={onOpen}
      className="card card-hover"
      style={{
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        alignItems: "flex-start",
        textAlign: "left",
        cursor: "pointer",
        flex: "1 1 250px",
        maxWidth: 320,
        minWidth: 220,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
        }}
      >
        <LogoTile id={connector.id} size={42} />
        {connected !== undefined && (
          <span
            className={connected ? "chip chip-hot" : "chip"}
            style={{ fontSize: 11, padding: "3px 9px" }}
          >
            {connected && <span className="status-dot hot" />}
            {connected
              ? t("connectors.connected")
              : t("connectors.notConnected")}
          </span>
        )}
      </div>
      <div>
        <div style={{ fontSize: 14.5, fontWeight: 700, marginBottom: 4 }}>
          {connector.name}
        </div>
        <div
          style={{
            fontSize: 12.5,
            color: "var(--text-muted)",
            lineHeight: 1.45,
          }}
        >
          {connector.desc}
        </div>
      </div>
      <div
        className="gradient-text"
        style={{
          marginTop: "auto",
          fontSize: 12,
          fontWeight: 700,
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
        }}
      >
        {connected
          ? t("connectors.manage")
          : t("connectors.connect")}
        <Icon name="chevronRight" size={13} />
      </div>
    </button>
  );
}

function ConnectorModal({
  connector,
  onClose,
}: {
  connector: Connector;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const Section = connector.Section;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,15,20,0.4)",
        zIndex: 200,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          borderRadius: 16,
          width: "min(560px, 100%)",
          maxHeight: "92vh",
          overflowY: "auto",
          boxShadow: "0 16px 56px rgba(15,15,20,0.18)",
        }}
      >
        <div
          style={{
            padding: "18px 24px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <LogoTile id={connector.id} size={44} />
            <div>
              <div style={{ fontSize: 17, fontWeight: 700 }}>
                {connector.name}
              </div>
              <div
                style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}
              >
                {connector.desc}
              </div>
            </div>
          </div>
          <button
            className="btn-icon"
            onClick={onClose}
            type="button"
            aria-label={t("common.close")}
          >
            <Icon name="x" size={18} />
          </button>
        </div>

        <div style={{ padding: 20 }}>
          <Section />
        </div>
      </div>
    </div>
  );
}
