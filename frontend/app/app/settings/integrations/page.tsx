"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getGmailStatus,
  getHubspotStatus,
  getNotionStatus,
  getOutlookStatus,
  getPipedriveStatus,
} from "@/lib/api";
import { BackendInfoCards } from "@/components/settings/BackendInfoCards";
import { CostSection } from "@/components/settings/CostSection";
import { useLocale, type TranslationKey } from "@/lib/i18n";

/**
 * Интеграции — Settings.dc.html. Карточки описывают, что даёт
 * подключение, без названий источников данных (те живут в админке
 * платформы). Настройка каждого коннектора — в маркетплейсе; здесь
 * статус и вход. Потолок затрат — внизу, как в макете.
 */

type CardState = "live" | "soon";

interface IntgCard {
  id: string;
  title: TranslationKey;
  desc: TranslationKey;
  state: CardState;
  href?: string;
  /** probe → подключён/нет; без него статус не показываем */
  status?: () => Promise<boolean>;
}

const CARDS: IntgCard[] = [
  {
    id: "telegram",
    title: "intg.telegram.title",
    desc: "intg.telegram.desc",
    state: "live",
    href: "/app/profile",
  },
  {
    id: "gmail",
    title: "intg.gmail.title",
    desc: "intg.gmail.desc",
    state: "live",
    href: "/app/connectors",
    status: () => getGmailStatus().then((s) => s.connected),
  },
  {
    id: "outlook",
    title: "intg.outlook.title",
    desc: "intg.outlook.desc",
    state: "live",
    href: "/app/connectors",
    status: () => getOutlookStatus().then((s) => s.connected),
  },
  {
    id: "openphone",
    title: "intg.openphone.title",
    desc: "intg.openphone.desc",
    state: "soon",
  },
  {
    id: "calendar",
    title: "intg.calendar.title",
    desc: "intg.calendar.desc",
    state: "soon",
  },
  {
    id: "hubspot",
    title: "intg.hubspot.title",
    desc: "intg.hubspot.desc",
    state: "live",
    href: "/app/connectors",
    status: () => getHubspotStatus().then((s) => s.connected),
  },
  {
    id: "pipedrive",
    title: "intg.pipedrive.title",
    desc: "intg.pipedrive.desc",
    state: "live",
    href: "/app/connectors",
    status: () => getPipedriveStatus().then((s) => s.connected),
  },
  {
    id: "notion",
    title: "intg.notion.title",
    desc: "intg.notion.desc",
    state: "live",
    href: "/app/connectors",
    status: () => getNotionStatus().then((s) => s.connected),
  },
  {
    id: "slack",
    title: "intg.slack.title",
    desc: "intg.slack.desc",
    state: "live",
    href: "/app/connectors",
  },
  {
    id: "sheets",
    title: "intg.sheets.title",
    desc: "intg.sheets.desc",
    state: "live",
    href: "/app/connectors",
  },
  {
    id: "webhooks",
    title: "intg.webhooks.title",
    desc: "intg.webhooks.desc",
    state: "live",
    href: "/app/settings/webhooks",
  },
  {
    id: "agencyos",
    title: "intg.agencyos.title",
    desc: "intg.agencyos.desc",
    state: "soon",
  },
];

export default function SettingsIntegrationsPage() {
  const { t } = useLocale();
  const [connected, setConnected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    for (const card of CARDS) {
      if (!card.status) continue;
      card
        .status()
        .then((ok) => {
          if (!cancelled)
            setConnected((prev) => ({ ...prev, [card.id]: ok }));
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, []);

  const statusDot = (card: IntgCard) => {
    if (card.state === "soon") {
      return (
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: 12,
            fontWeight: 800,
            color: "var(--warm)",
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--warm)",
            }}
          />
          {t("intg.st.soon")}
        </span>
      );
    }
    const state = connected[card.id];
    if (state === undefined) return null;
    return (
      <span
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: 12,
          fontWeight: 800,
          color: state ? "var(--accent)" : "var(--text-dim)",
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: state ? "var(--accent)" : "var(--text-dim)",
          }}
        />
        {state ? t("intg.st.connected") : t("intg.st.notConnected")}
      </span>
    );
  };

  return (
    <>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 12,
          marginBottom: 16,
        }}
      >
        {CARDS.map((card) => (
          <div
            key={card.id}
            className="card"
            style={{
              padding: "18px 20px",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span style={{ fontSize: 15, fontWeight: 800 }}>
                {t(card.title)}
              </span>
              {statusDot(card)}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
                flexGrow: 1,
              }}
            >
              {t(card.desc)}
            </div>
            {card.state === "soon" ? (
              <div
                style={{
                  border: "1.5px dashed var(--border)",
                  borderRadius: 10,
                  fontSize: 13.5,
                  fontWeight: 700,
                  color: "var(--text-dim)",
                  padding: "8px 0",
                  textAlign: "center",
                }}
              >
                {t("intg.unavailable")}
              </div>
            ) : connected[card.id] === false ? (
              <Link
                href={card.href ?? "/app/connectors"}
                className="btn btn-primary btn-sm"
                style={{ justifyContent: "center" }}
              >
                {t("intg.connect")}
              </Link>
            ) : (
              <Link
                href={card.href ?? "/app/connectors"}
                className="btn btn-ghost btn-sm"
                style={{ justifyContent: "center" }}
              >
                {t("intg.configure")}
              </Link>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 16 }}>
        <Link href="/app/connectors" className="btn btn-ghost btn-sm">
          {t("intg.marketplaceBtn")}
        </Link>
      </div>

      <CostSection />

      <div
        style={{
          fontSize: 12.5,
          color: "var(--text-dim)",
          marginTop: 4,
          lineHeight: 1.5,
        }}
      >
        {t("intg.footer")}
      </div>

      <BackendInfoCards />
    </>
  );
}
