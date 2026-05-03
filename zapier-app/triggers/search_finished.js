'use strict';

const { subscribe, unsubscribe, performFromHook } = require('../utils/restHook');
const { sampleSearch } = require('../utils/samples');

// `search.finished` fires from the search pipeline when a query closes
// (success or failure — `error` is non-null on failure). Use this to
// kick off downstream "the leads are ready" workflows.
const extract = (body) => {
  const search = body && body.data && body.data.search;
  if (!search || !search.id) {
    return null;
  }
  return {
    ...search,
    delivery_id: body.delivery_id,
    delivered_at: body.delivered_at,
  };
};

module.exports = {
  key: 'search_finished',
  noun: 'Search',
  display: {
    label: 'Search Finished',
    description:
      'Triggers when a Convioo search completes (whether it found leads or failed).',
  },
  operation: {
    type: 'hook',
    performSubscribe: subscribe('search.finished'),
    performUnsubscribe: unsubscribe,
    perform: performFromHook(extract),
    sample: sampleSearch,
  },
};
