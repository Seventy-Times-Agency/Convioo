"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  connectNotion,
  disconnectNotion,
  getNotionStatus,
  listNotionDatabases,
  setNotionDatabase,
  startNotionAuthorize,
  type NotionDatabaseChoice,
  type NotionIntegrationStatus,
} from "@/lib/api";
import { showError } from "@/lib/toast";
import { confirmAsync } from "@/lib/confirm";
import { useLocale } from "@/lib/i18n";

const EMPTY: NotionIntegrationStatus = {
  connected: false,
  token_preview: null,
  database_id: null,
  workspace_name: null,
  owner_email: null,
  auth_type: null,
  updated_at: null,
};

export function NotionSection() {
  const { t } = useLocale();
  const [status, setStatus] = useState<NotionIntegrationStatus | null>(null);
  const [editing, setEditing] = useState(false);
  const [token, setToken] = useState("");
  const [databaseId, setDatabaseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState<NotionDatabaseChoice[] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const refresh = async () => {
    try {
      const next = await getNotionStatus();
      setStatus(next);
      // OAuth-installed users without a chosen database land back here
      // from the consent redirect; auto-open the picker so they can
      // finish in one click.
      if (next.connected && next.auth_type === "oauth" && !next.database_id) {
        setPickerOpen(true);
      }
    } catch {
      setStatus(EMPTY);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  // Strip ?notion=connected from the URL after the callback redirect
  // so a refresh doesn't keep "connected" in the location bar.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("notion") === "connected") {
      params.delete("notion");
      const qs = params.toString();
      const next = window.location.pathname + (qs ? `?${qs}` : "");
      window.history.replaceState({}, "", next);
    }
  }, []);

  const startOAuth = async () => {
    setBusy(true);
    try {
      const { url } = await startNotionAuthorize();
      window.location.href = url;
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const openPicker = async () => {
    setPickerOpen(true);
    if (picker !== null) return;
    try {
      const { items } = await listNotionDatabases();
      setPicker(items);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const choosePicker = async (id: string) => {
    setBusy(true);
    try {
      const next = await setNotionDatabase(id);
      setStatus(next);
      setPickerOpen(false);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token.trim() || !databaseId.trim()) return;
    setBusy(true);
    try {
      const next = await connectNotion({
        token: token.trim(),
        databaseId: databaseId.trim(),
      });
      setStatus(next);
      setEditing(false);
      setToken("");
      setDatabaseId("");
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!(await confirmAsync(t("settings.notion.disconnectConfirm")))) return;
    setBusy(true);
    try {
      await disconnectNotion();
      setStatus(EMPTY);
      setPicker(null);
      setPickerOpen(false);
    } catch (e) {
      showError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        {t("settings.notion.eyebrow")}
      </div>

      {status === null ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("common.loading")}</div>
      ) : status.connected && !editing ? (
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
              {status.workspace_name ?? t("settings.notion.connectedTitle")}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.5 }}>
              {t("settings.notion.authMethod")}{" "}
              <span>
                {status.auth_type === "oauth"
                  ? t("settings.notion.authOauth")
                  : "Internal Integration Token"}
              </span>
              <br />
              {t("settings.notion.databaseLabel")}{" "}
              <span style={{ fontFamily: "var(--font-mono)" }}>
                {status.database_id ?? t("settings.notion.databaseNotChosen")}
              </span>
              {status.owner_email && (
                <>
                  <br />
                  {t("settings.notion.accountLabel")} <span>{status.owner_email}</span>
                </>
              )}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6 }}>
              {t("settings.notion.exportHint")}
            </div>
            {pickerOpen && (
              <NotionDatabasePicker
                items={picker}
                busy={busy}
                onPick={(id) => void choosePicker(id)}
                onCancel={() => setPickerOpen(false)}
                onLoad={() => void openPicker()}
              />
            )}
          </div>
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            {!pickerOpen && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void openPicker()}
                disabled={busy}
              >
                {status.database_id
                  ? t("settings.notion.changeDatabase")
                  : t("settings.notion.chooseDatabase")}
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setEditing(true)}
              disabled={busy}
            >
              {t("settings.notion.changeConnection")}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => void disconnect()}
              disabled={busy}
              style={{ color: "var(--cold)" }}
            >
              {t("settings.notion.disconnect")}
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div
            style={{
              display: "flex",
              gap: 10,
              alignItems: "center",
              padding: 12,
              border: "1px solid var(--border)",
              borderRadius: 10,
              background: "var(--surface)",
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 2 }}>
                {t("settings.notion.oauthTitle")}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {t("settings.notion.oauthDesc")}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void startOAuth()}
              disabled={busy}
            >
              {busy ? "..." : "Connect Notion"}
            </button>
          </div>
          <div
            style={{
              fontSize: 11,
              color: "var(--text-dim)",
              textTransform: "uppercase",
              letterSpacing: 0.5,
              textAlign: "center",
            }}
          >
            {t("settings.notion.orManual")}
          </div>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5, margin: 0 }}>
              {t("settings.notion.step1Before")}{" "}
              <a
                href="https://www.notion.so/my-integrations"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--accent)" }}
              >
                notion.so/my-integrations
              </a>
              {t("settings.notion.step1After")}
              <br />
              {t("settings.notion.step2")}
              <br />
              {t("settings.notion.step3")}
            </p>
            <input
              className="input"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="ntn_•••••••••••••"
              autoComplete="off"
            />
            <input
              className="input"
              value={databaseId}
              onChange={(e) => setDatabaseId(e.target.value)}
              placeholder="Database ID (32 hex)"
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="submit"
                className="btn btn-sm"
                disabled={busy || !token.trim() || !databaseId.trim()}
              >
                {busy ? t("settings.notion.checkingAccess") : t("settings.connector.connect")}
              </button>
              {status?.connected && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setEditing(false)}
                  disabled={busy}
                >
                  {t("common.cancel")}
                </button>
              )}
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function NotionDatabasePicker({
  items,
  busy,
  onPick,
  onCancel,
  onLoad,
}: {
  items: NotionDatabaseChoice[] | null;
  busy: boolean;
  onPick: (id: string) => void;
  onCancel: () => void;
  onLoad: () => void;
}) {
  const { t } = useLocale();
  useEffect(() => {
    if (items === null) onLoad();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      style={{
        marginTop: 10,
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: 12,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          {t("settings.notion.pickerTitle")}
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onCancel}
          disabled={busy}
        >
          {t("common.cancel")}
        </button>
      </div>
      {items === null ? (
        <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
          {t("settings.notion.pickerLoading")}
        </div>
      ) : items.length === 0 ? (
        <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
          {t("settings.notion.pickerEmpty")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {items.map((db) => (
            <button
              key={db.id}
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => onPick(db.id)}
              disabled={busy}
              style={{
                justifyContent: "flex-start",
                fontSize: 13,
                textAlign: "left",
              }}
            >
              {db.icon && <span style={{ marginRight: 6 }}>{db.icon}</span>}
              {db.title}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
