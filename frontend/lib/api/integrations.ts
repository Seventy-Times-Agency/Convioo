import { request } from "./_core";

export interface NotionIntegrationStatus {
  connected: boolean;
  token_preview: string | null;
  database_id: string | null;
  workspace_name: string | null;
  owner_email: string | null;
  auth_type: string | null;
  updated_at: string | null;
}

export interface NotionDatabaseChoice {
  id: string;
  title: string;
  icon: string | null;
  url: string | null;
}

export interface NotionExportItem {
  lead_id: string;
  notion_url: string | null;
  error: string | null;
}

export interface HubspotIntegrationStatus {
  connected: boolean;
  portal_id: number | null;
  account_email: string | null;
  scope: string | null;
  expires_at: string | null;
}

export interface HubspotExportItem {
  lead_id: string;
  contact_id: string | null;
  error: string | null;
}

export interface PipedriveIntegrationStatus {
  connected: boolean;
  api_domain: string | null;
  account_email: string | null;
  scope: string | null;
  expires_at: string | null;
  default_pipeline_id: number | null;
  default_stage_id: number | null;
}

export interface PipedriveStage {
  id: number;
  name: string;
  pipeline_id: number;
  order_nr: number;
}

export interface PipedrivePipeline {
  id: number;
  name: string;
  stages: PipedriveStage[];
}

export interface PipedriveExportItem {
  lead_id: string;
  person_id: string | null;
  deal_id: string | null;
  error: string | null;
}

// ── Notion ──────────────────────────────────────────────────────────

export async function getNotionStatus(): Promise<NotionIntegrationStatus> {
  return request<NotionIntegrationStatus>("/api/v1/integrations/notion");
}

export async function connectNotion(args: {
  token: string;
  databaseId: string;
}): Promise<NotionIntegrationStatus> {
  return request<NotionIntegrationStatus>("/api/v1/integrations/notion", {
    method: "PUT",
    body: JSON.stringify({
      token: args.token,
      database_id: args.databaseId,
    }),
  });
}

export async function disconnectNotion(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/v1/integrations/notion", {
    method: "DELETE",
  });
}

export async function startNotionAuthorize(): Promise<{
  url: string;
  state: string;
}> {
  return request<{ url: string; state: string }>(
    "/api/v1/integrations/notion/authorize",
  );
}

export async function setNotionDatabase(
  databaseId: string,
): Promise<NotionIntegrationStatus> {
  return request<NotionIntegrationStatus>(
    "/api/v1/integrations/notion/database",
    {
      method: "PATCH",
      body: JSON.stringify({ database_id: databaseId }),
    },
  );
}

export async function listNotionDatabases(): Promise<{
  items: NotionDatabaseChoice[];
}> {
  return request<{ items: NotionDatabaseChoice[] }>(
    "/api/v1/integrations/notion/databases",
  );
}

export async function exportLeadsToNotion(
  leadIds: string[],
): Promise<{
  items: NotionExportItem[];
  success_count: number;
  failure_count: number;
}> {
  return request<{
    items: NotionExportItem[];
    success_count: number;
    failure_count: number;
  }>("/api/v1/leads/export-to-notion", {
    method: "POST",
    body: JSON.stringify({ lead_ids: leadIds }),
  });
}

export async function syncFromNotion(): Promise<{
  items: NotionExportItem[];
  success_count: number;
  failure_count: number;
}> {
  return request<{
    items: NotionExportItem[];
    success_count: number;
    failure_count: number;
  }>("/api/v1/integrations/notion/sync", { method: "POST" });
}

// ── HubSpot ─────────────────────────────────────────────────────────

export async function getHubspotStatus(): Promise<HubspotIntegrationStatus> {
  return request<HubspotIntegrationStatus>("/api/v1/integrations/hubspot");
}

export async function startHubspotAuthorize(): Promise<{
  url: string;
  state: string;
}> {
  return request<{ url: string; state: string }>(
    "/api/v1/integrations/hubspot/authorize",
  );
}

export async function disconnectHubspot(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/v1/integrations/hubspot", {
    method: "DELETE",
  });
}

export async function exportLeadsToHubspot(
  leadIds: string[],
): Promise<{
  items: HubspotExportItem[];
  success_count: number;
  failure_count: number;
}> {
  return request<{
    items: HubspotExportItem[];
    success_count: number;
    failure_count: number;
  }>("/api/v1/leads/export-to-hubspot", {
    method: "POST",
    body: JSON.stringify({ lead_ids: leadIds }),
  });
}

// ── Pipedrive ────────────────────────────────────────────────────────

export async function getPipedriveStatus(): Promise<PipedriveIntegrationStatus> {
  return request<PipedriveIntegrationStatus>(
    "/api/v1/integrations/pipedrive",
  );
}

export async function startPipedriveAuthorize(): Promise<{
  url: string;
  state: string;
}> {
  return request<{ url: string; state: string }>(
    "/api/v1/integrations/pipedrive/authorize",
  );
}

export async function disconnectPipedrive(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/v1/integrations/pipedrive", {
    method: "DELETE",
  });
}

export async function listPipedrivePipelines(): Promise<{
  items: PipedrivePipeline[];
}> {
  return request<{ items: PipedrivePipeline[] }>(
    "/api/v1/integrations/pipedrive/pipelines",
  );
}

export async function setPipedriveConfig(args: {
  defaultPipelineId: number;
  defaultStageId: number;
}): Promise<PipedriveIntegrationStatus> {
  return request<PipedriveIntegrationStatus>(
    "/api/v1/integrations/pipedrive/config",
    {
      method: "PUT",
      body: JSON.stringify({
        default_pipeline_id: args.defaultPipelineId,
        default_stage_id: args.defaultStageId,
      }),
    },
  );
}

export async function exportLeadsToPipedrive(
  leadIds: string[],
): Promise<{
  items: PipedriveExportItem[];
  success_count: number;
  failure_count: number;
}> {
  return request<{
    items: PipedriveExportItem[];
    success_count: number;
    failure_count: number;
  }>("/api/v1/leads/export-to-pipedrive", {
    method: "POST",
    body: JSON.stringify({ lead_ids: leadIds }),
  });
}
