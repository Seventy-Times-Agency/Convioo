"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AuthShell } from "@/components/AuthShell";
import { Icon } from "@/components/Icon";
import {
  ApiError,
  acceptInvite,
  previewInvite,
  type InvitePreview,
} from "@/lib/api";
import { getCurrentUser } from "@/lib/auth";
import { setActiveWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

const RETURN_KEY = "convioo.returnTo";

export default function JoinPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { t } = useLocale();
  const token = params.token;

  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => {
    setSignedIn(getCurrentUser() !== null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    previewInvite(token)
      .then((p) => !cancelled && setPreview(p))
      .catch((e) => {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const remaining = preview
    ? Math.max(0, Math.floor((new Date(preview.expires_at).getTime() - now) / 1000))
    : 0;
  const liveExpired = preview ? remaining <= 0 || preview.expired : false;
  const accepted = preview?.accepted ?? false;

  const onAccept = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const team = await acceptInvite(token);
      setActiveWorkspace({
        kind: "team",
        team_id: team.id,
        team_name: team.name,
      });
      router.push("/app");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e),
      );
      setSubmitting(false);
    }
  };

  const stashReturn = () => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RETURN_KEY, `/join/${token}`);
    }
  };

  return (
    <AuthShell title={t("invite.title")}>
      {error && !preview && (
        <div style={{ color: "var(--cold)", fontSize: 14 }}>{error}</div>
      )}

      {preview && (
        <>
          <div
            style={{
              fontSize: 18,
              fontWeight: 600,
              marginBottom: 8,
            }}
          >
            {preview.team_name}
          </div>
          <div style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 18 }}>
            {t("invite.subtitle", { role: preview.role })}
          </div>

          {accepted && (
            <div
              className="card"
              style={{
                padding: 14,
                fontSize: 13,
                color: "var(--cold)",
                borderColor: "var(--cold)",
                marginBottom: 16,
              }}
            >
              {t("invite.alreadyUsed")}
            </div>
          )}

          {!accepted && liveExpired && (
            <div
              className="card"
              style={{
                padding: 14,
                fontSize: 13,
                color: "var(--cold)",
                borderColor: "var(--cold)",
                marginBottom: 16,
              }}
            >
              {t("invite.expired")}
            </div>
          )}

          {!accepted && !liveExpired && (
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-muted)",
                marginBottom: 18,
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <Icon name="clock" size={12} />
              {t("invite.expiresIn", { mm: formatRemaining(remaining) })}
            </div>
          )}

          {signedIn === false && !liveExpired && !accepted && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <Link
                href="/login"
                onClick={stashReturn}
                className="btn btn-lg"
                style={{ justifyContent: "center" }}
              >
                {t("invite.signInToAccept")} <Icon name="arrow" size={14} />
              </Link>
              <Link
                href="/register"
                onClick={stashReturn}
                className="btn btn-ghost btn-lg"
                style={{ justifyContent: "center" }}
              >
                {t("invite.registerToAccept")}
              </Link>
            </div>
          )}

          {signedIn && !liveExpired && !accepted && (
            <button
              type="button"
              className="btn btn-lg"
              onClick={onAccept}
              disabled={submitting}
              style={{ width: "100%", justifyContent: "center" }}
            >
              {submitting ? t("common.loading") : t("invite.accept")}{" "}
              <Icon name="check" size={14} />
            </button>
          )}

          {error && (
            <div
              style={{
                marginTop: 14,
                fontSize: 13,
                color: "var(--cold)",
              }}
            >
              {error}
            </div>
          )}
        </>
      )}
    </AuthShell>
  );
}

function formatRemaining(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
