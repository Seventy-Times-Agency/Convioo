'use strict';

const { sampleLead, sampleLeadTag } = require('../utils/samples');

// PUT /api/v1/leads/{lead_id}/tags REPLACES the lead's tag set, so to
// "add" a tag we first GET the current set, append, then PUT. We also
// expose a dynamic dropdown of the user's existing tags so they don't
// have to copy UUIDs by hand.

const listTags = async (z, bundle) => {
  const response = await z.request({
    url: '/api/v1/tags',
    method: 'GET',
  });
  const items = (response.data && response.data.items) || [];
  return items.map((t) => ({
    id: t.id,
    name: t.name,
    color: t.color,
  }));
};

const perform = async (z, bundle) => {
  const { lead_id, tag_id } = bundle.inputData;

  // GET the lead so we can preserve existing tag assignments. The list
  // endpoint hydrates user_tags; the single-lead PATCH response also
  // returns user_tags.
  const leadResp = await z.request({
    url: `/api/v1/leads?limit=500`,
    method: 'GET',
  });
  const all = (leadResp.data && leadResp.data.items) || [];
  const lead = all.find((l) => l.id === lead_id);
  const existingTagIds = lead
    ? (lead.user_tags || []).map((t) => t.id)
    : [];

  const tagIds = Array.from(new Set([...existingTagIds, tag_id]));

  const response = await z.request({
    url: `/api/v1/leads/${encodeURIComponent(lead_id)}/tags`,
    method: 'PUT',
    body: { tag_ids: tagIds },
  });
  return {
    lead_id,
    added_tag_id: tag_id,
    tags: (response.data && response.data.items) || [],
  };
};

module.exports = {
  key: 'add_lead_tag',
  noun: 'Tag',
  display: {
    label: 'Add Tag to Lead',
    description:
      'Attach a user-defined chip tag to a lead. Existing tags on the lead are preserved.',
  },
  operation: {
    perform,
    inputFields: [
      {
        key: 'lead_id',
        label: 'Lead ID',
        type: 'string',
        required: true,
      },
      {
        key: 'tag_id',
        label: 'Tag',
        type: 'string',
        required: true,
        dynamic: 'tagsList.id.name',
        helpText:
          'Pick a tag from your Convioo workspace, or paste a tag UUID.',
      },
    ],
    sample: {
      lead_id: sampleLead.id,
      added_tag_id: sampleLeadTag.id,
      tags: [sampleLeadTag],
    },
  },
};

// Side-export: the "tagsList" hidden trigger that powers the dynamic
// dropdown on tag_id. Wired into index.js under triggers.
module.exports.tagsList = {
  key: 'tagsList',
  noun: 'Tag',
  display: {
    label: 'List Tags',
    description: 'Internal — populates the tag dropdown on actions.',
    hidden: true,
  },
  operation: {
    perform: listTags,
    sample: sampleLeadTag,
  },
};
