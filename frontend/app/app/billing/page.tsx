import { redirect } from "next/navigation";

// Подписок нет — инструмент внутренний. Старый адрес ведёт на расходы.
export default function BillingPage() {
  redirect("/app/settings/billing");
}
