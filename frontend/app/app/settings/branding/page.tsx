import { redirect } from "next/navigation";

/** Брендинг переехал во вкладку «Компания». */
export default function SettingsBrandingRedirect() {
  redirect("/app/settings");
}
