import { toast } from "sonner";
import { readUiLang, pickUiLang } from "@/lib/uiLang";

/**
 * Non-blocking confirmation via sonner toast.
 * Drop-in async replacement for window.confirm().
 *
 * Callers pass an already-localized `message` (via t(...)). The two button
 * labels are localized here from the persisted UI language so they match.
 */
export function confirmAsync(message: string): Promise<boolean> {
  const lang = readUiLang();
  const confirmLabel = pickUiLang(lang, {
    ru: "Подтвердить",
    uk: "Підтвердити",
    en: "Confirm",
  });
  const cancelLabel = pickUiLang(lang, { ru: "Отмена", uk: "Скасувати", en: "Cancel" });
  return new Promise((resolve) => {
    let resolved = false;
    const settle = (value: boolean) => {
      if (!resolved) {
        resolved = true;
        resolve(value);
      }
    };
    toast(message, {
      duration: 8000,
      action: { label: confirmLabel, onClick: () => settle(true) },
      cancel: { label: cancelLabel, onClick: () => settle(false) },
      onDismiss: () => settle(false),
    });
  });
}
