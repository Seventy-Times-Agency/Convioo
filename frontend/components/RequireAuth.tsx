"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { getCurrentUser, type CurrentUser } from "@/lib/auth";

/**
 * Client-side gate for the workspace shell. Reads the user out of
 * localStorage; if missing, sends the visitor to /login.
 *
 * Renders nothing while the check is running so authenticated pages
 * never flash for an unauthenticated visitor.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null | "loading">("loading");

  useEffect(() => {
    const u = getCurrentUser();
    if (!u) {
      router.replace("/login");
      setUser(null);
      return;
    }
    setUser(u);
  }, [router]);

  if (user === "loading" || user === null) return null;
  return <>{children}</>;
}
