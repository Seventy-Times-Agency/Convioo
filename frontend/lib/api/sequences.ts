import { request } from "./_core";

export interface SequenceStep {
  day: number;
  subject: string;
  body: string;
}

export interface Sequence {
  id: string;
  name: string;
  steps: SequenceStep[];
  created_at: string;
}

export async function listSequences(): Promise<Sequence[]> {
  const data = await request<Sequence[] | { items: Sequence[] }>(
    "/api/v1/sequences",
  );
  if (Array.isArray(data)) return data;
  return Array.isArray(data?.items) ? data.items : [];
}

export async function createSequence(
  name: string,
  steps: SequenceStep[],
): Promise<Sequence> {
  return request<Sequence>("/api/v1/sequences", {
    method: "POST",
    body: JSON.stringify({ name, steps }),
  });
}
