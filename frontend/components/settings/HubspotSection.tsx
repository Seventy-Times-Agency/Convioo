"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  disconnectHubspot,
  getHubspotStatus,
  startHubspotAuthorize,
  type HubspotIntegrationStatus,
} from "@/lib/api";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { useLocale } from "@/lib/i18n";

export function HubspotSection() {
  const { t } = useLocale();
  const [status, setStatus] = useState<HubspotIntegrationStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHubspotStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            connected: false,
            portal_id: null,
            account_email: null,
            scope: null,
            expires_at: null,
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = async () => {
    setBusy(true);
    try {
      const { url } = await startHubspotAuthorize();
      window.location.href = url;
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!(await confirmAsync(t("settings.hubspot.disconnectConfirm")))) return;
    setBusy(true);
    try {
      await disconnectHubspot();
      setStatus({
        connected: false,
        portal_id: null,
        account_email: null,
        scope: null,
        expires_at: null,
      });
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.hubspot.eyebrow")}
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
      ) : status.connected ? (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 16,
            justifyContent: "space-between",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              {status.account_email
                ? t("settings.connectedAs", { email: status.account_email })
                : t("settings.connected")}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              Portal ID:{" "}
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {status.portal_id ?? t("common.none")}
              </span>
              <br />
              {t("settings.hubspot.scopes")}
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void disconnect()}
            disabled={busy}
            style={{ color: "var(--cold)" }}
          >
            {t("settings.disconnect")}
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            {t("settings.hubspot.intro")}
          </p>
          <div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void connect()}
              disabled={busy}
            >
              {busy ? "..." : t("settings.hubspot.connectBtn")}
            </button>
          </div>
        </div>
      )}

    </div>
  );
}
