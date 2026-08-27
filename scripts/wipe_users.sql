-- Wipe all user-generated data from production.
--
-- Run this once when you want to reset the site to a clean state
-- (e.g. closing the public registration and starting fresh).
--
-- All FK relationships from user-data tables have ON DELETE CASCADE,
-- so truncating these two top-level tables sweeps the rest:
--   users   -> search_queries -> leads -> lead_custom_fields,
--                                          lead_activities, lead_tasks
--           -> team_memberships, team_invites, team_seen_leads,
--              lead_marks, email_verification_tokens,
--              assistant_memories, user_seen_leads,
--              outreach_templates, user_audit_logs
--   teams   -> (any orphaned rows after users are gone)
--
-- This does NOT touch the alembic_version table — schema stays intact.
--
-- USAGE (Railway Postgres → Data tab → Query):
--   1. Confirm you're on the right project / environment.
--   2. Paste the entire BEGIN...COMMIT block.
--   3. Read the row counts before COMMIT to sanity-check.
--   4. COMMIT.
--
-- If you want to abort midway, replace COMMIT with ROLLBACK.

BEGIN;

-- Snapshot what we're about to delete.
SELECT 'users'                       AS table_name, count(*) AS rows FROM users
UNION ALL SELECT 'teams',                            count(*) FROM teams
UNION ALL SELECT 'search_queries',                   count(*) FROM search_queries
UNION ALL SELECT 'leads',                            count(*) FROM leads
UNION ALL SELECT 'team_memberships',                 count(*) FROM team_memberships
UNION ALL SELECT 'team_invites',                     count(*) FROM team_invites
UNION ALL SELECT 'team_seen_leads',                  count(*) FROM team_seen_leads
UNION ALL SELECT 'lead_marks',                       count(*) FROM lead_marks
UNION ALL SELECT 'email_verification_tokens',        count(*) FROM email_verification_tokens
UNION ALL SELECT 'assistant_memories',               count(*) FROM assistant_memories
UNION ALL SELECT 'user_seen_leads',                  count(*) FROM user_seen_leads
UNION ALL SELECT 'outreach_templates',               count(*) FROM outreach_templates
UNION ALL SELECT 'lead_custom_fields',               count(*) FROM lead_custom_fields
UNION ALL SELECT 'lead_activities',                  count(*) FROM lead_activities
UNION ALL SELECT 'lead_tasks',                       count(*) FROM lead_tasks
UNION ALL SELECT 'user_audit_logs',                  count(*) FROM user_audit_logs
ORDER BY table_name;

-- Single-shot wipe. CASCADE chases every FK with ON DELETE CASCADE.
TRUNCATE TABLE users, teams RESTART IDENTITY CASCADE;

-- Re-snapshot to confirm everything is empty.
SELECT 'users'                       AS table_name, count(*) AS rows FROM users
UNION ALL SELECT 'teams',                            count(*) FROM teams
UNION ALL SELECT 'search_queries',                   count(*) FROM search_queries
UNION ALL SELECT 'leads',                            count(*) FROM leads
UNION ALL SELECT 'team_memberships',                 count(*) FROM team_memberships
UNION ALL SELECT 'team_invites',                     count(*) FROM team_invites
UNION ALL SELECT 'team_seen_leads',                  count(*) FROM team_seen_leads
UNION ALL SELECT 'lead_marks',                       count(*) FROM lead_marks
UNION ALL SELECT 'email_verification_tokens',        count(*) FROM email_verification_tokens
UNION ALL SELECT 'assistant_memories',               count(*) FROM assistant_memories
UNION ALL SELECT 'user_seen_leads',                  count(*) FROM user_seen_leads
UNION ALL SELECT 'outreach_templates',               count(*) FROM outreach_templates
UNION ALL SELECT 'lead_custom_fields',               count(*) FROM lead_custom_fields
UNION ALL SELECT 'lead_activities',                  count(*) FROM lead_activities
UNION ALL SELECT 'lead_tasks',                       count(*) FROM lead_tasks
UNION ALL SELECT 'user_audit_logs',                  count(*) FROM user_audit_logs
ORDER BY table_name;

COMMIT;
