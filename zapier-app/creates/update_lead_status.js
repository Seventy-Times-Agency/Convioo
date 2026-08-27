'use strict';

const { sampleLead } = require('../utils/samples');

// PATCH /api/v1/leads/{lead_id} — only the lead_status field is sent.
// The backend validates the value against the team's pipeline (or the
// legacy hardcoded set in personal mode) and writes a LeadActivity row.
const perform = async (z, bundle) => {
  const { lead_id, lead_status } = bundle.inputData;
  const response = await z.request({
    url: `/api/v1/leads/${encodeURIComponent(lead_id)}`,
    method: 'PATCH',
    body: { lead_status },
  });
  return response.data;
};

module.exports = {
  key: 'update_lead_status',
  noun: 'Lead',
  display: {
    label: 'Update Lead Status',
    description: 'Move a lead to a different pipeline status.',
  },
  operation: {
    perform,
    inputFields: [
      {
        key: 'lead_id',
        label: 'Lead ID',
        type: 'string',
        required: true,
        helpText: 'UUID of the lead. Map this from a "New Lead" trigger step.',
      },
      {
        key: 'lead_status',
        label: 'New Status',
        type: 'string',
        required: true,
        helpText:
          'Status key. Personal mode: new, contacted, replied, won, archived. ' +
          'Team mode: any key from your custom pipeline.',
      },
    ],
    sample: sampleLead,
  },
};
