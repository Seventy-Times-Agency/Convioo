import { redirect } from "next/navigation";

/** Коннекторы убраны: почта и Telegram — в профиле, общие подключения
 * команды — в «Настройки → Подключения». */
export default function ConnectorsMoved() {
  redirect("/app/settings/connections");
}
