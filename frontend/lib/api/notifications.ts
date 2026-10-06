import { request } from "./_core";

/** Лента уведомлений в приложении (колокольчик в левой панели). */
export type NotificationKind =
  | "hot_reply"
  | "overdue"
  | "escalation"
  | "batch"
  | "goal"
  | "letter_waiting"
  | "search_done"
  | "budget"
  | "digest";

export interface AppNotification {
  id: string;
  kind: NotificationKind | string;
  title: string;
  body: string | null;
  link: string | null;
  important: boolean;
  created_at: string;
  read: boolean;
}

export interface NotificationCounts {
  unread: number;
  unread_important: number;
}

export interface NotificationFeed extends NotificationCounts {
  items: AppNotification[];
}

export async function getNotifications(important = false): Promise<NotificationFeed> {
  return request<NotificationFeed>(
    `/api/v1/notifications${important ? "?important=true" : ""}`,
  );
}

export async function getUnreadNotifications(): Promise<NotificationCounts> {
  return request<NotificationCounts>("/api/v1/notifications/unread");
}

export async function markNotificationsRead(
  args: { ids: string[] } | { all: true },
): Promise<NotificationCounts> {
  return request<NotificationCounts>("/api/v1/notifications/read", {
    method: "POST",
    body: JSON.stringify(args),
  });
}
