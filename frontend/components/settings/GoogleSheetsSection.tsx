"use client";

import { useState } from "react";
import { request } from "@/lib/api/_core";

export function GoogleSheetsSection() {
  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await request("/api/v1/users/me", {
        method: "PATCH",
        body: JSON.stringify({ google_sheets_spreadsheet_id: spreadsheetId }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Google Sheets
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Новые лиды автоматически добавляются в вашу таблицу после каждого поиска.
        Поделитесь таблицей с сервисным аккаунтом (email в настройках платформы).
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          style={{
            flex: 1, padding: "6px 10px", borderRadius: 6,
            border: "1px solid var(--border)", fontSize: 13,
            background: "var(--surface)", color: "var(--text)",
          }}
          placeholder="ID таблицы (из URL Google Sheets)"
          value={spreadsheetId}
          onChange={(e) => setSpreadsheetId(e.target.value)}
        />
        <button
          onClick={save}
          disabled={saving || !spreadsheetId}
          style={{
            padding: "6px 16px", borderRadius: 6, fontSize: 13,
            background: "var(--accent)", color: "#fff",
            border: "none", cursor: "pointer", opacity: saving ? 0.6 : 1,
          }}
        >
          {saved ? "Сохранено" : saving ? "..." : "Сохранить"}
        </button>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 8 }}>
        ID таблицы — часть URL между /d/ и /edit
      </div>
    </div>
  );
}
