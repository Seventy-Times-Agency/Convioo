import { redirect } from "next/navigation";

// Публичных тарифов нет: пока это внутренний инструмент команды.
export default function PricingPage() {
  redirect("/register");
}
