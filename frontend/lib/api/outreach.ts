import { request } from "./_core";

export interface OutreachTemplate {
  id: string;
  user_id: number;
  team_id: string | null;
  name: string;
  subject: string | null;
  body: string;
  tone: string;
  created_at: string;
  updated_at: string;
}

export async function listOutreachTemplates(opts: { teamId?: string } = {}): Promise<{
  items: OutreachTemplate[];
}> {
  const params = new URLSearchParams();
  if (opts.teamId) params.set("team_id", opts.teamId);
  const qs = params.toString();
  return request<{ items: OutreachTemplate[] }>(
    `/api/v1/templates${qs ? `?${qs}` : ""}`,
  );
}

export async function createOutreachTemplate(input: {
  name: string;
  subject?: string | null;
  body: string;
  tone?: string;
  teamId?: string;
}): Promise<OutreachTemplate> {
  return request<OutreachTemplate>("/api/v1/templates", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      subject: input.subject ?? null,
      body: input.body,
      tone: input.tone ?? "professional",
      team_id: input.teamId ?? null,
    }),
  });
}

export async function updateOutreachTemplate(
  id: string,
  patch: { name?: string; subject?: string | null; body?: string; tone?: string },
): Promise<OutreachTemplate> {
  return request<OutreachTemplate>(`/api/v1/templates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteOutreachTemplate(id: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/v1/templates/${id}`, {
    method: "DELETE",
  });
}
