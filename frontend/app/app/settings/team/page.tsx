"use client";

import Link from "next/link";

export default function SettingsTeamPage() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Команда
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
          marginBottom: 14,
        }}
      >
        Управление командой — приглашения, роли, описание команды,
        общий пайплайн — живёт на отдельной странице.
      </div>
      <Link href="/app/team" className="btn btn-sm">
        Открыть страницу команды
      </Link>
    </div>
  );
}
