import { redirect } from "next/navigation";

/** Доставляемость переехала во вкладку «Почта». */
export default function SettingsDeliverabilityRedirect() {
  redirect("/app/settings/mail");
}
