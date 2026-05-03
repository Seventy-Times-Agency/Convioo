'use strict';

// Shared REST-hook plumbing. Each trigger declares which event it cares
// about (e.g. `lead.created`) and we register a single-event subscription
// against POST /api/v1/webhooks. The subscription id comes back in the
// response and is passed to performUnsubscribe.

const subscribe = (eventType) => async (z, bundle) => {
  const response = await z.request({
    url: '/api/v1/webhooks',
    method: 'POST',
    body: {
      target_url: bundle.targetUrl,
      event_types: [eventType],
      description: `Zapier — ${eventType}`,
    },
  });
  return response.data;
};

const unsubscribe = async (z, bundle) => {
  const id = bundle.subscribeData && bundle.subscribeData.id;
  if (!id) {
    return {};
  }
  const response = await z.request({
    url: `/api/v1/webhooks/${id}`,
    method: 'DELETE',
    skipThrowForStatus: true,
  });
  // 404 is fine — the user may have deleted the webhook from the UI.
  return response.data || {};
};

// REST-hook `perform`: the request body Convioo POSTed to bundle.targetUrl
// is exposed as bundle.cleanedRequest. Each trigger pulls the relevant
// slice out of `data` and returns it as a single-item list so Zapier can
// run downstream steps once per event.
const performFromHook = (extract) => async (z, bundle) => {
  const body = bundle.cleanedRequest || {};
  const record = extract(body);
  if (!record) {
    return [];
  }
  return [record];
};

module.exports = { subscribe, unsubscribe, performFromHook };
