'use strict';

const { sampleLead } = require('../utils/samples');

// Convioo doesn't expose a single-lead POST endpoint — leads are born
// from search pipelines or CSV imports. The CSV-import route accepts a
// JSON list of rows so we treat "create one lead" as a one-row import,
// which lands the lead inside a synthetic search session named "Zapier".
// This mirrors what /app/import does in the UI.

const perform = async (z, bundle) => {
  const {
    name,
    website,
    region,
    phone,
    category,
    label,
    team_id,
  } = bundle.inputData;

  const body = {
    label: label || 'Zapier import',
    rows: [
      {
        name,
        website: website || null,
        region: region || null,
        phone: phone || null,
        category: category || null,
        extras: {},
      },
    ],
  };
  if (team_id) {
    body.team_id = team_id;
  }

  const response = await z.request({
    url: '/api/v1/searches/import-csv',
    method: 'POST',
    body,
  });

  // The import endpoint returns {search_id, inserted, skipped}. Fetch
  // the resulting lead so the Zap can reference its id / score in
  // downstream steps. We pull from the per-search lead listing.
  const { search_id, inserted, skipped } = response.data || {};
  let lead = null;
  if (search_id && inserted > 0) {
    const leadsResp = await z.request({
      url: `/api/v1/searches/${search_id}/leads`,
      method: 'GET',
    });
    const items = (leadsResp.data && leadsResp.data.items) || [];
    lead = items[0] || null;
  }

  return {
    search_id,
    inserted,
    skipped,
    lead,
  };
};

module.exports = {
  key: 'create_lead',
  noun: 'Lead',
  display: {
    label: 'Create Lead',
    description:
      'Adds a new lead to your CRM under a synthetic "Zapier import" session. ' +
      'Useful for piping leads in from forms, spreadsheets, or other CRMs.',
  },
  operation: {
    perform,
    inputFields: [
      {
        key: 'name',
        label: 'Company / Lead Name',
        type: 'string',
        required: true,
      },
      {
        key: 'website',
        label: 'Website',
        type: 'string',
        required: false,
        helpText: 'Convioo will scrape it for AI scoring.',
      },
      {
        key: 'region',
        label: 'Region / City',
        type: 'string',
        required: false,
      },
      {
        key: 'phone',
        label: 'Phone',
        type: 'string',
        required: false,
      },
      {
        key: 'category',
        label: 'Category',
        type: 'string',
        required: false,
      },
      {
        key: 'label',
        label: 'Session Label',
        type: 'string',
        required: false,
        default: 'Zapier import',
        helpText:
          'Name shown under /app/sessions for the synthetic import session.',
      },
      {
        key: 'team_id',
        label: 'Team ID',
        type: 'string',
        required: false,
        helpText: 'UUID of the team to drop the lead into. Leave blank for personal.',
      },
    ],
    sample: {
      search_id: '00000000-0000-0000-0000-000000000000',
      inserted: 1,
      skipped: 0,
      lead: sampleLead,
    },
  },
};
