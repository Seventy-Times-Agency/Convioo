import { API_BASE, request } from "./_core";

/**
 * Wave 4 — white-label client reports.
 *
 * Two surfaces:
 *  - Team branding (agency name / logo / accent colour) edited from
 *    settings and stamped onto every public report.
 *  - Shareable, tokenised report links generated from a search. The
 *    public endpoints take NO credentials — they're meant to be sent
 *    to the agency's own clients.
 */

export interface Branding {
  brand_name: string | null;
  /** base64 data URL, e.g. ``data:image/png;base64,...`` */
  brand_logo: string | null;
  /** ``#RRGGBB`` */
  brand_color: string | null;
}

export interface BrandingPatch {
  brand_name?: string | null;
  brand_logo?: string | null;
  brand_color?: string | null;
}

export interface CreateReportResult {
  report_id: string;
  token: string;
  /** ``/report/<token>`` */
  share_path: string;
  expires_at: string | null;
}

export interface ReportSummary {
  report_id: string;
  token: string;
  title: string | null;
  search_id: string;
  revoked: boolean;
  expires_at: string | null;
  created_at: string;
  share_path: string;
}

export interface PublicReportTopLead {
  name: string | null;
  score: number | null;
  lead_status: string | null;
  contact_email: string | null;
  phone: string | null;
  website: string | null;
}

export interface PublicReportStats {
  total_leads: number;
  hot_leads: number;
  leads_with_email: number;
  leads_with_valid_email: number;
  leads_with_phone: number;
  avg_score: number | null;
  replied: number;
  top_leads: PublicReportTopLead[];
  insights: string | null;
  niche: string | null;
  region: string | null;
  generated_at: string | null;
}

export interface PublicReport {
  brand_name: string | null;
  brand_logo: string | null;
  brand_color: string | null;
  title: string | null;
  generated_at: string | null;
  stats: PublicReportStats;
}

export async function getBranding(teamId: string): Promise<Branding> {
  return request<Branding>(`/api/v1/teams/${teamId}/branding`);
}

export async function updateBranding(
  teamId: string,
  patch: BrandingPatch,
): Promise<Branding> {
  return request<Branding>(`/api/v1/teams/${teamId}/branding`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function createReport(
  searchId: string,
  opts: { title?: string | null; expiresInDays?: number | null } = {},
): Promise<CreateReportResult> {
  return request<CreateReportResult>(`/api/v1/searches/${searchId}/report`, {
    method: "POST",
    body: JSON.stringify({
      title: opts.title ?? null,
      expires_in_days: opts.expiresInDays ?? null,
    }),
  });
}

export async function listReports(): Promise<ReportSummary[]> {
  const res = await request<{ reports: ReportSummary[] }>("/api/v1/reports");
  return res.reports;
}

export async function revokeReport(reportId: string): Promise<{ ok: true }> {
  return request<{ ok: true }>(`/api/v1/reports/${reportId}`, {
    method: "DELETE",
  });
}

/**
 * Public report payload. No auth required — the shared ``request``
 * helper still sends cookies, which the backend ignores for this
 * endpoint, so it's safe to reuse.
 */
export async function getPublicReport(token: string): Promise<PublicReport> {
  return request<PublicReport>(`/api/v1/reports/public/${token}`);
}

/** Absolute URL for the public PDF download (used as an <a href>). */
export function publicReportPdfUrl(token: string): string {
  return `${API_BASE}/api/v1/reports/public/${token}/download.pdf`;
}
