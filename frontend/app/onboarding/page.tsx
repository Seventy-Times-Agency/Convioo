"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Legacy onboarding route. Registration now collects only name + age,
 * and the rest of the profile is filled from inside the workspace
 * (manually on /app/profile or by chatting with Henry). This page
 * exists only to keep older verification / invite emails pointing
 * here from 404'ing — it bounces straight to /app.
 */
export default function OnboardingPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/app/profile");
  }, [router]);
  return null;
}
