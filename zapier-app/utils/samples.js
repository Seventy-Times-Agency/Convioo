'use strict';

// Static samples for trigger "test" runs in the Zap editor. Mirrors the
// payload shape that core/services/webhooks.py:serialize_lead /
// serialize_search produce, wrapped in the envelope _dispatch builds.

const sampleLead = {
  id: '0d0c6c6e-1b9a-4f99-9f3c-3b91a5e4d7a1',
  query_id: 'a45e6c1d-2c5b-4ab3-9d8e-89bb14f9b6a2',
  name: 'Joe’s Roofing Co.',
  category: 'Roofing contractor',
  address: '123 Main St, Brooklyn, NY 11201',
  phone: '+1 718 555 0142',
  website: 'https://joesroofing.example.com',
  rating: 4.7,
  reviews_count: 138,
  score_ai: 82,
  lead_status: 'new',
  owner_user_id: 1,
  tags: ['hot', 'mid-size'],
  summary: 'Established Brooklyn roofer with 4.7★ across 138 reviews.',
  advice: 'Lead with your fastest-quote angle — they brag about turnaround.',
  created_at: '2026-05-03T10:11:12+00:00',
};

const sampleSearch = {
  id: 'a45e6c1d-2c5b-4ab3-9d8e-89bb14f9b6a2',
  user_id: 1,
  team_id: null,
  niche: 'roofing companies',
  region: 'New York, NY',
  status: 'finished',
  leads_count: 47,
  avg_score: 64.2,
  created_at: '2026-05-03T10:00:00+00:00',
  finished_at: '2026-05-03T10:11:14+00:00',
  error: null,
};

const sampleLeadTag = {
  id: 'b1aaf5fe-2db5-4f0d-9c66-9c2b8b7c52a4',
  name: 'priority',
  color: '#FF5630',
};

module.exports = { sampleLead, sampleSearch, sampleLeadTag };
