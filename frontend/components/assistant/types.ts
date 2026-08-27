import type {
  AssistantField,
  AssistantMode,
  ConsultMessage,
  PendingAction,
} from "@/lib/api";

export interface ChatMsg extends ConsultMessage {
  mode?: AssistantMode;
  /** Profile field Henry was waiting on after THIS turn. Echoed back
   *  on the next user turn so a short reply (e.g. "Berlin") gets
   *  routed to the field he asked about. */
  awaiting_field?: AssistantField | null;
  /** Confirm-before-write: actions Henry proposed on this turn,
   *  awaiting an in-chat confirmation from the user. */
  pending_actions?: PendingAction[] | null;
  /** Filled when Henry's previous turn proposed actions and the user
   *  confirmed them — replaces the pending card with a "записано" mark. */
  applied_actions?: PendingAction[] | null;
  /** Optional 1-liner Henry attached to a pending proposal. */
  suggestion_summary?: string | null;
  /** Set after the user clicks dismiss on the pending card; hides the
   *  buttons so the same card can't be re-confirmed. */
  resolved?: "applied" | "dismissed";
}
