import { request, requireUserId } from "./_core";
import { type CurrentUser } from "../auth";

export interface AuthUser extends CurrentUser {
  email: string | null;
  email_verified: boolean;
  onboarded: boolean;
  onboarding_tour_completed: boolean;
}

export const REFERRAL_COOKIE_NAME = "convioo_ref";

function readReferralCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split(";")
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${REFERRAL_COOKIE_NAME}=`));
  if (!match) return null;
  const value = decodeURIComponent(match.slice(REFERRAL_COOKIE_NAME.length + 1));
  return value || null;
}

export async function registerUser(args: {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  ageRange?: string | null;
  gender?: string | null;
  registrationPassword?: string | null;
}): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({
      first_name: args.firstName,
      last_name: args.lastName,
      email: args.email,
      password: args.password,
      age_range: args.ageRange ?? null,
      gender: args.gender ?? null,
      registration_password: args.registrationPassword ?? null,
      referral_code: readReferralCookie(),
    }),
  });
}

export async function loginUser(
  email: string,
  password: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function verifyEmail(token: string): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function resendVerification(
  email: string,
): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>("/api/v1/auth/resend-verification", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function changeEmail(
  newEmail: string,
  password: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/users/me/change-email", {
    method: "POST",
    body: JSON.stringify({ new_email: newEmail, password }),
  });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/users/me/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export async function fetchAuthMe(): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/me");
}

export async function logoutCurrentSession(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" });
}

export async function logoutAllSessions(): Promise<{ revoked: number }> {
  return request<{ revoked: number }>("/api/v1/auth/logout-all", {
    method: "POST",
  });
}

export async function forgotPassword(
  email: string,
): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function forgotEmail(
  recoveryEmail: string,
): Promise<{ sent: boolean }> {
  return request<{ sent: boolean }>("/api/v1/auth/forgot-email", {
    method: "POST",
    body: JSON.stringify({ recovery_email: recoveryEmail }),
  });
}

export interface SessionInfo {
  id: string;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export async function listMySessions(): Promise<{
  sessions: SessionInfo[];
  count: number;
}> {
  return request<{ sessions: SessionInfo[]; count: number }>(
    "/api/v1/auth/sessions",
  );
}

export async function revokeMySession(
  sessionId: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/auth/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export interface ApiKey {
  id: string;
  label: string | null;
  token_preview: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
}

export interface ApiKeyCreated {
  id: string;
  token: string;
  label: string | null;
  token_preview: string;
  created_at: string;
}

export async function listMyApiKeys(): Promise<{ items: ApiKey[] }> {
  return request<{ items: ApiKey[] }>("/api/v1/auth/api-keys");
}

export async function createApiKey(label: string | null): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>("/api/v1/auth/api-keys", {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export async function revokeApiKey(id: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/auth/api-keys/${id}`, {
    method: "DELETE",
  });
}

// completeOnboardingTour lives here since it touches auth user state
export async function completeOnboardingTour(): Promise<AuthUser> {
  return request<AuthUser>("/api/v1/users/me/onboarding-complete", {
    method: "PATCH",
  });
}

// unused in module but kept for callers
export { requireUserId };
