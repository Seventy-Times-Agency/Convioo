import type { ConsultMessage, ConsultSlot } from "@/lib/api";

export interface ChatMsg extends ConsultMessage {
  pending?: boolean;
}

export type OfferSource = "profile" | "custom";
