"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children?: ReactNode;
  /** Footer row — usually the action buttons. */
  footer?: ReactNode;
  width?: number;
}

/** Centered dialog on a dimmed scrim. Esc / scrim click closes.
 * Replaces every native prompt()/confirm() surface per the etalon. */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 440,
}: ModalProps) {
  const scrimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={scrimRef}
      className="anim-scrim"
      onMouseDown={(e) => {
        if (e.target === scrimRef.current) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(30, 27, 22, 0.45)",
        zIndex: 120,
        display: "grid",
        placeItems: "center",
        padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="card anim-pop"
        style={{
          width: "100%",
          maxWidth: width,
          // Длинное содержимое прокручивается внутри окна, заголовок и
          // кнопки остаются на месте.
          maxHeight: "calc(100dvh - 32px)",
          padding: 24,
          boxShadow: "var(--shadow-lg)",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {title != null && (
          <div style={{ fontSize: 16, fontWeight: 700, flexShrink: 0 }}>{title}</div>
        )}
        <div
          style={{
            flex: "1 1 auto",
            minHeight: 0,
            overflowY: "auto",
            overscrollBehavior: "contain",
            display: "flex",
            flexDirection: "column",
            gap: 16,
            // Место под полосу прокрутки, чтобы текст не прилипал к ней.
            margin: "0 -8px",
            padding: "0 8px",
          }}
        >
          {children}
        </div>
        {footer != null && (
          <div
            style={{
              display: "flex",
              gap: 8,
              justifyContent: "flex-end",
              flexWrap: "wrap",
              flexShrink: 0,
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
