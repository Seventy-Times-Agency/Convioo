/**
 * Legacy barrel — kept so existing imports from "@/lib/api" keep working.
 * All logic has moved to "@/lib/api/<resource>" modules.
 * New code should import directly from the relevant module file.
 */

export * from "./api/index";
