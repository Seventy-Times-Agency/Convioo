"use client";

import { useEffect, useState } from "react";

import {
  type AuthCreds,
  getApiBase,
  pingHealth,
  readAuth,
  writeAuth,
} from "@/lib/api";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; db: boolean; commit: string }
  | { status: "error"; message: string };

export default function SettingsPage() {
  const [creds, setCreds] = useState<AuthCreds | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [savedKey, setSavedKey] = useState(false);
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    const c = readAuth();
    setCreds(c);
    setApiKey(c?.apiKey ?? "");
    pingHealth()
      .then((h) =>
        setHealth({ status: "ok", db: h.db, commit: h.commit })
      )
      .catch((e: Error) =>
        setHealth({ status: "error", message: e.message })
      );
  }, []);

  if (!creds) return null;

  const saveKey = (e: React.FormEvent) => {
    e.preventDefault();
    writeAuth({ ...creds, apiKey: apiKey.trim() || undefined });
    setSavedKey(true);
    setTimeout(() => setSavedKey(false), 2000);
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 24,
        maxWidth: 720,
      }}
    >
      <header>
        <div className="eyebrow" style={{ marginBottom: 8 }}>
          Settings
        </div>
        <h1
          style={{
            fontSize: 30,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            margin: 0,
          }}
        >
          Workspace settings
        </h1>
      </header>

      {/* Backend connection */}
      <section className="card" style={{ padding: 24 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>
          Backend
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "140px 1fr",
            gap: "10px 16px",
            alignItems: "baseline",
            fontSize: 14,
          }}
        >
          <span style={{ color: "var(--text-muted)" }}>API base</span>
          <span
            className="mono"
            style={{
              wordBreak: "break-all",
              color: "var(--text)",
            }}
          >
            {getApiBase()}
          </span>

          <span style={{ color: "var(--text-muted)" }}>Status</span>
          <span>
            {health.status === "loading" && (
              <span style={{ color: "var(--text-muted)" }}>checking…</span>
            )}
            {health.status === "ok" && (
              <span style={{ color: health.db ? "var(--hot)" : "var(--cold)" }}>
                {health.db ? "healthy" : "db unreachable"}
              </span>
            )}
            {health.status === "error" && (
              <span style={{ color: "var(--cold)" }}>
                unreachable — {health.message}
              </span>
            )}
          </span>

          {health.status === "ok" && (
            <>
              <span style={{ color: "var(--text-muted)" }}>Commit</span>
              <span className="mono" style={{ color: "var(--text)" }}>
                {health.commit || "unknown"}
              </span>
            </>
          )}
        </div>
      </section>

      {/* API key */}
      <form onSubmit={saveKey} className="card" style={{ padding: 24 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>
          API key
        </div>
        <p
          style={{
            fontSize: 13.5,
            color: "var(--text-muted)",
            lineHeight: 1.55,
            margin: "0 0 14px",
          }}
        >
          Leave empty while the backend runs in open mode (the default).
          When the operator sets <span className="mono">WEB_API_KEY</span> on
          the server, paste the same value here so your browser can reach
          protected routes.
        </p>
        <input
          className="input"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="(empty = open mode)"
          style={{ marginBottom: 12 }}
        />
        <div
          style={{ display: "flex", alignItems: "center", gap: 12 }}
        >
          <button type="submit" className="btn">
            Save key
          </button>
          {savedKey && (
            <span style={{ fontSize: 13, color: "var(--hot)" }}>
              Saved.
            </span>
          )}
        </div>
      </form>

      {/* Identity */}
      <section className="card" style={{ padding: 24 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>
          Identity
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "140px 1fr",
            gap: "10px 16px",
            alignItems: "baseline",
            fontSize: 14,
          }}
        >
          <span style={{ color: "var(--text-muted)" }}>Name</span>
          <span>{creds.displayName}</span>
          <span style={{ color: "var(--text-muted)" }}>Workspace id</span>
          <span className="mono">{creds.userId}</span>
        </div>
        <p
          style={{
            fontSize: 12.5,
            color: "var(--text-dim)",
            marginTop: 14,
            lineHeight: 1.55,
          }}
        >
          Workspace id is derived from your name; change the name on the
          Profile page to start a fresh workspace.
        </p>
      </section>
    </div>
  );
}
