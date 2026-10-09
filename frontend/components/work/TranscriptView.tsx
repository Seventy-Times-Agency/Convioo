"use client";

import { useLocale } from "@/lib/i18n";

type Seg = { speaker: string; text: string; start?: number };

const mmss = (s?: number) =>
  s == null ? "" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/** Расшифровка как диалог: менеджер слева, клиент справа, у реплики —
 * время от начала разговора. */
export function TranscriptView({ segments }: { segments: Seg[] }) {
  const { t } = useLocale();
  return (
    <div className="tr-dialog">
      {segments.map((s, i) => {
        const client = s.speaker === "client" || s.speaker === "s1";
        const who =
          s.speaker === "rep"
            ? t("calls.speakerRep")
            : s.speaker === "client"
              ? t("calls.speakerClient")
              : t("ca.speakerN", { n: Number(s.speaker.replace(/\D/g, "") || 0) + 1 });
        const showWho = i === 0 || segments[i - 1].speaker !== s.speaker;
        return (
          <div key={i} className={"tr-msg " + (client ? "client" : "rep")}>
            {showWho && (
              <div className="tr-who">
                {who}
                {s.start != null && <span>{mmss(s.start)}</span>}
              </div>
            )}
            <div className="tr-bubble">{s.text}</div>
          </div>
        );
      })}
    </div>
  );
}
