"use client";

import { useState } from "react";
import { createRoot } from "react-dom/client";
import { Button, Input, Modal } from "@/components/ui";
import { pickUiLang, readUiLang } from "@/lib/uiLang";

/**
 * Async replacement for window.prompt(): renders an etalon Modal with
 * a single input. Resolves the entered string, or null on cancel.
 *
 * Callers pass an already-localized `message` (via t(...)); the two
 * button labels are localized here from the persisted UI language.
 */
export function promptAsync(
  message: string,
  defaultValue = "",
): Promise<string | null> {
  if (typeof document === "undefined") return Promise.resolve(null);
  const lang = readUiLang();
  const okLabel = pickUiLang(lang, {
    ru: "Сохранить",
    uk: "Зберегти",
    en: "Save",
  });
  const cancelLabel = pickUiLang(lang, {
    ru: "Отмена",
    uk: "Скасувати",
    en: "Cancel",
  });

  return new Promise((resolve) => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);

    const settle = (value: string | null) => {
      root.unmount();
      host.remove();
      resolve(value);
    };

    function PromptDialog() {
      const [value, setValue] = useState(defaultValue);
      const submit = () => settle(value.trim() || null);
      return (
        <Modal
          open
          onClose={() => settle(null)}
          title={message}
          footer={
            <>
              <Button variant="ghost" size="sm" onClick={() => settle(null)}>
                {cancelLabel}
              </Button>
              <Button size="sm" onClick={submit}>
                {okLabel}
              </Button>
            </>
          }
        >
          <Input
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
        </Modal>
      );
    }

    root.render(<PromptDialog />);
  });
}
