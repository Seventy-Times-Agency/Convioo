"use client";

import { useState } from "react";
import { callRecordingUrl } from "@/lib/api";
import { useLocale } from "@/lib/i18n";

/** Плеер записи звонка. Если браузер не смог её проиграть, вместо
 * немого «ошибка» — понятная причина и ссылка скачать файл. */
export function RecordingPlayer({ callId }: { callId: string }) {
  const { t } = useLocale();
  const [failed, setFailed] = useState(false);
  const src = callRecordingUrl(callId);
  if (failed) {
    return (
      <div style={{ fontSize: 12.5, color: "var(--text-muted)", display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span>{t("ca.playFailed")}</span>
        <a href={src} download={`call-${callId}.wav`} style={{ color: "var(--accent)", fontWeight: 600 }}>
          {t("ca.download")}
        </a>
      </div>
    );
  }
  return (
    <audio
      controls
      preload="none"
      src={src}
      onError={() => setFailed(true)}
      style={{ width: "100%", height: 34 }}
    />
  );
}
