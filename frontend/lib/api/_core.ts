/**
 * Core HTTP plumbing for the Convioo API client.
 *
 * Pulled out of ``lib/api.ts`` so per-resource modules under
 * ``lib/api/`` can share the same ``request`` helper without
 * importing back from the legacy barrel (which would create a
 * circular dependency).
 */

import { getCurrentUser } from "../auth";

const RAW_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
export const API_BASE = RAW_BASE.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function requireUserId(): number {
  const u = getCurrentUser();
  if (!u) {
    throw new ApiError("Not signed in", 401, null);
  }
  return u.user_id;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  // Same-origin first: Next.js rewrites /api/* to the Railway service
  // so the auth cookie travels as first-party. Fallback to the raw
  // API base if rewrites are disabled (e.g. running the SPA standalone
  // without the rewrite layer).
  const target =
    path.startsWith("/api/") || path === "/health" || path === "/metrics"
      ? path
      : `${API_BASE}${path}`;
  const res = await fetch(target, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    credentials: "include",
    cache: "no-store",
  });
  let body: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : null) ?? `${res.status} ${res.statusText}`;
    throw new ApiError(detail, res.status, body);
  }
  return body as T;
}
