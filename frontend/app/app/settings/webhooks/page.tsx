import { redirect } from "next/navigation";

/** Раздел переехал после пересборки настроек. */
export default function Moved() {
  redirect("/app/settings/tech");
}
