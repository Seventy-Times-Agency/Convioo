import { redirect } from "next/navigation";

/** Управление командой живёт на своём экране. */
export default function SettingsTeamRedirect() {
  redirect("/app/team");
}
