'use strict';

const { subscribe, unsubscribe, performFromHook } = require('../utils/restHook');
const { sampleLead } = require('../utils/samples');

// Convioo emits `lead.created` whenever a search pipeline lands a lead in
// the CRM (web search, CSV import, Notion sync). Payload shape mirrors
// serialize_lead (see core/services/webhooks.py).
const extract = (body) => {
  const lead = body && body.data && body.data.lead;
  if (!lead || !lead.id) {
    return null;
  }
  return {
    ...lead,
    // Zapier needs an `id` field on the record so dedup works across
    // replays. The lead.id UUID is already unique.
    id: lead.id,
    delivery_id: body.delivery_id,
    delivered_at: body.delivered_at,
  };
};

module.exports = {
  key: 'new_lead',
  noun: 'Lead',
  display: {
    label: 'New Lead',
    description: 'Triggers when a new lead lands in your Convioo CRM.',
  },
  operation: {
    type: 'hook',
    performSubscribe: subscribe('lead.created'),
    performUnsubscribe: unsubscribe,
    perform: performFromHook(extract),
    sample: sampleLead,
  },
};
