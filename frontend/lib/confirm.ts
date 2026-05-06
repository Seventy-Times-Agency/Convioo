import { toast } from "sonner";

/**
 * Non-blocking confirmation via sonner toast.
 * Drop-in async replacement for window.confirm().
 */
export function confirmAsync(message: string): Promise<boolean> {
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
      action: { label: "Подтвердить", onClick: () => settle(true) },
      cancel: { label: "Отмена", onClick: () => settle(false) },
      onDismiss: () => settle(false),
    });
  });
}
