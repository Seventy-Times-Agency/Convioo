/**
 * Звонок из браузера через Telnyx WebRTC.
 *
 * Бэкенд выдаёт JWT (POST /telephony/webrtc-token), SDK поднимает
 * WebSocket к Telnyx и голос по WebRTC. Клиент один на вкладку:
 * токен живёт сутки, мы запрашиваем новый, когда прошлый протух.
 * SDK трогает window, поэтому импортируется лениво — только в
 * момент первого звонка, а не при сборке страницы.
 */

import { getWebrtcToken } from "@/lib/api";

export type BrowserCallState =
  | "connecting"
  | "ringing"
  | "active"
  | "held"
  | "ended"
  | "failed";

export interface BrowserCallHandle {
  hangup: () => void;
  mute: (on: boolean) => void;
}

type TelnyxCall = {
  state: string;
  hangup: () => void;
  muteAudio: () => void;
  unmuteAudio: () => void;
};

type TelnyxClient = {
  connect: () => void;
  disconnect: () => void;
  on: (event: string, cb: (payload: unknown) => void) => void;
  off: (event: string) => void;
  newCall: (opts: Record<string, unknown>) => TelnyxCall;
  updateToken?: (token: string) => void;
};

let client: TelnyxClient | null = null;
let clientTeamId: string | null = null;
let tokenExpiresAt = 0;
let readyPromise: Promise<void> | null = null;

async function ensureClient(teamId: string): Promise<TelnyxClient> {
  const now = Date.now();
  if (client && clientTeamId === teamId && now < tokenExpiresAt - 60_000) {
    if (readyPromise) await readyPromise;
    return client;
  }
  if (client) {
    try {
      client.disconnect();
    } catch {
      // уже отключён
    }
    client = null;
  }
  const { token, expires_in } = await getWebrtcToken(teamId);
  const mod = await import("@telnyx/webrtc");
  const TelnyxRTC = (mod as { TelnyxRTC: new (o: Record<string, unknown>) => TelnyxClient }).TelnyxRTC;
  const next = new TelnyxRTC({ login_token: token });
  clientTeamId = teamId;
  tokenExpiresAt = now + Math.max(60, expires_in) * 1000;
  readyPromise = new Promise<void>((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error("telnyx: connection timeout")),
      15_000,
    );
    next.on("telnyx.ready", () => {
      clearTimeout(timer);
      resolve();
    });
    next.on("telnyx.error", (err) => {
      clearTimeout(timer);
      reject(err instanceof Error ? err : new Error("telnyx: connection error"));
    });
  });
  next.connect();
  client = next;
  await readyPromise;
  return next;
}

function mapState(raw: string): BrowserCallState | null {
  switch (raw) {
    case "new":
    case "requesting":
    case "trying":
    case "early":
      return "connecting";
    case "ringing":
      return "ringing";
    case "active":
      return "active";
    case "held":
      return "held";
    case "hangup":
    case "destroy":
      return "ended";
    default:
      return null;
  }
}

/** Набрать клиента из вкладки. ``onState`` получает переходы
 *  соединения; ``ended`` приходит один раз, когда разговор завершён
 *  любой стороной. */
export async function placeBrowserCall(opts: {
  teamId: string;
  destination: string;
  callerNumber?: string | null;
  onState: (state: BrowserCallState) => void;
}): Promise<BrowserCallHandle> {
  const c = await ensureClient(opts.teamId);
  let ended = false;
  const call = c.newCall({
    destinationNumber: opts.destination,
    callerNumber: opts.callerNumber ?? undefined,
    audio: true,
    video: false,
  });
  c.on("telnyx.notification", (payload) => {
    const n = payload as { type?: string; call?: TelnyxCall };
    if (n.type !== "callUpdate" || !n.call || n.call !== call) return;
    const state = mapState(n.call.state);
    if (!state) return;
    if (state === "ended") {
      if (ended) return;
      ended = true;
    }
    opts.onState(state);
  });
  return {
    hangup: () => {
      try {
        call.hangup();
      } catch {
        // уже завершён
      }
    },
    mute: (on) => (on ? call.muteAudio() : call.unmuteAudio()),
  };
}

/** Проверка, что браузер даст микрофон; без него звонок из вкладки
 *  невозможен, и кнопка должна открыть tel: как раньше. */
export async function microphoneAvailable(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices) return false;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    return true;
  } catch {
    return false;
  }
}
