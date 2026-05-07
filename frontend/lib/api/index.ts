/**
 * Barrel re-export for @/lib/api/* modules.
 * Import from "@/lib/api" for backward compatibility,
 * or directly from "@/lib/api/<resource>" for clarity.
 */

export * from "./_core";
export * from "./admin";
export * from "./auth";
export * from "./billing";
export * from "./gmail";
export * from "./integrations";
export * from "./leads";
export * from "./lead_statuses";
export * from "./outreach";
export * from "./outlook";
export * from "./profile";
export * from "./saved_searches";
export * from "./search";
export * from "./segments";
export * from "./team_analytics";
export * from "./teams";
export * from "./webhooks";
