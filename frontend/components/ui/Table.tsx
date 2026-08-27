"use client";

import type { HTMLAttributes, ReactNode } from "react";

export interface TableProps extends HTMLAttributes<HTMLTableElement> {
  children?: ReactNode;
  /** Max height for the scroll container; header stays sticky. */
  maxHeight?: number | string;
}

/** Etalon table: uppercase dim header, row hover, horizontal scroll
 * on narrow screens. Compose with plain <thead>/<tbody>/<tr>/<th>/<td>. */
export function Table({ children, maxHeight, className, ...rest }: TableProps) {
  return (
    <div
      style={{
        overflowX: "auto",
        ...(maxHeight !== undefined ? { overflowY: "auto", maxHeight } : {}),
      }}
    >
      <table
        className={["tbl", className ?? ""].filter(Boolean).join(" ")}
        {...rest}
      >
        {children}
      </table>
    </div>
  );
}
