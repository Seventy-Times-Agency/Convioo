/**
 * Notion public OAuth — start consent, list databases, pick one.
 *
 * The legacy internal-token connect flow lives in ``lib/api.ts`` as
 * ``connectNotion`` (PUT body of ``token + database_id``). The OAuth
 * helpers here only handle the new path: ``authorize`` opens a Notion
 * consent page, the callback lands the bot token in our DB, then the
 * SPA picks a database from ``listNotionDatabases``.
 */

import { request } from "./_core";

export async function startNotionAuthorize(): Promise<{
  url: string;
  state: string;
}> {
  return request<{ url: string; state: string }>(
    "/api/v1/integrations/notion/authorize",
  );
}

export interface NotionDatabaseChoice {
  id: string;
  title: string;
  icon: string | null;
  url: string | null;
}

export async function listNotionDatabases(): Promise<{
  items: NotionDatabaseChoice[];
}> {
  return request<{ items: NotionDatabaseChoice[] }>(
    "/api/v1/integrations/notion/databases",
  );
}

export async function selectNotionDatabase(
  databaseId: string,
): Promise<unknown> {
  return request("/api/v1/integrations/notion/database", {
    method: "PUT",
    body: JSON.stringify({ database_id: databaseId }),
  });
}
