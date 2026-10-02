import type { TranslationKey } from "@/lib/i18n";

/** Каноническая роль — зеркало серверного normalize_role: легаси
 *  member → manager, viewer → sales, всё незнакомое — sales (самая
 *  узкая). Сервер отдаёт роль как есть, поэтому каждая роль из API
 *  проходит через эту функцию в lib/api/teams.ts. */
export function normalizeRole(role: string | undefined | null): string {
  const r = (role ?? "").toLowerCase().trim();
  if (r === "owner" || r === "admin" || r === "manager" || r === "sales")
    return r;
  if (r === "member") return "manager";
  return "sales";
}

/** Человеческое название роли. Легаси-значения из старого прототипа
 *  нормализуются так же, как на сервере: member → менеджер,
 *  viewer → селз. */
export function roleLabel(
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string,
  role: string,
): string {
  if (role === "owner") return t("team.role.owner");
  if (role === "admin") return t("team.role.admin");
  if (role === "manager") return t("team.role.manager");
  if (role === "sales") return t("team.role.sales");
  if (role === "member") return t("team.role.manager");
  if (role === "viewer") return t("team.role.sales");
  return role;
}
