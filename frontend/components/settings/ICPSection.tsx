"use client";

import { useRef, useState } from "react";

interface ICPProfile {
  industries?: string[];
  typical_size?: string;
  pain_points?: string[];
  keywords?: string[];
  notes?: string;
}

export function ICPSection() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [icp, setIcp] = useState<ICPProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/users/me/icp-profile`,
        { method: "POST", body: form, credentials: "include" }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }
      const data = await res.json();
      setIcp(data.icp_profile);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Ошибка загрузки");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        ICP Learning — Идеальный профиль клиента
      </div>
      <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
        Загрузите CSV с вашими лучшими клиентами. Claude автоматически извлечёт паттерны
        и персонализирует поиск и cold email под ваш ICP.
      </p>
      <p style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 12 }}>
        Формат: любые колонки (название, ниша, адрес, выручка, отрасль и т.д.)
      </p>
      <button
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        style={{
          padding: "7px 18px", borderRadius: 6, fontSize: 13,
          background: "var(--accent)", color: "#fff",
          border: "none", cursor: uploading ? "not-allowed" : "pointer",
          opacity: uploading ? 0.6 : 1,
        }}
      >
        {uploading ? "Анализирую..." : "Загрузить CSV"}
      </button>
      <input ref={inputRef} type="file" accept=".csv" style={{ display: "none" }} onChange={handleFile} />
      {error && <div style={{ fontSize: 12, color: "var(--error)", marginTop: 8 }}>{error}</div>}
      {icp && (
        <div style={{ marginTop: 16, padding: 12, background: "var(--surface-2)", borderRadius: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Извлечённый ICP:</div>
          {icp.industries && (
            <div style={{ fontSize: 12, marginBottom: 4 }}>
              Ниши: {icp.industries.join(", ")}
            </div>
          )}
          {icp.typical_size && (
            <div style={{ fontSize: 12, marginBottom: 4 }}>Размер: {icp.typical_size}</div>
          )}
          {icp.notes && (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{icp.notes}</div>
          )}
        </div>
      )}
    </div>
  );
}
