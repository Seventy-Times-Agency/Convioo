'use strict';

const { subscribe, unsubscribe, performFromHook } = require('../utils/restHook');
const { sampleLead } = require('../utils/samples');

// `lead.status_changed` fires from PATCH /api/v1/leads/{id} when the
// lead_status field actually moves. The payload carries the full lead
// plus from_status/to_status/actor_user_id.
const extract = (body) => {
  const data = body && body.data;
  if (!data || !data.lead || !data.lead.id) {
    return null;
  }
  return {
    ...data.lead,
    id: `${data.lead.id}:${body.delivery_id}`, // unique per status change
    lead_id: data.lead.id,
    from_status: data.from_status,
    to_status: data.to_status,
    actor_user_id: data.actor_user_id,
    delivery_id: body.delivery_id,
    delivered_at: body.delivered_at,
  };
};

module.exports = {
  key: 'lead_status_changed',
  noun: 'Lead',
  display: {
    label: 'Lead Status Changed',
    description:
      'Triggers when a lead moves between statuses (e.g. new → contacted).',
  },
  operation: {
    type: 'hook',
    performSubscribe: subscribe('lead.status_changed'),
    performUnsubscribe: unsubscribe,
    perform: performFromHook(extract),
    sample: {
      ...sampleLead,
      lead_id: sampleLead.id,
      from_status: 'new',
      to_status: 'contacted',
      actor_user_id: 1,
    },
  },
};
