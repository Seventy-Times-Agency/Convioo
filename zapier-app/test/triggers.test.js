'use strict';

const zapier = require('zapier-platform-core');
const App = require('../index');
const { sampleLead, sampleSearch } = require('../utils/samples');

const appTester = zapier.createAppTester(App);
zapier.tools.env.inject();

const authData = {
  apiKey: 'test-key',
  apiUrl: 'https://api.convioo.com',
};

describe('REST hook triggers extract from cleanedRequest', () => {
  test('new_lead returns the lead from the webhook envelope', async () => {
    const bundle = {
      authData,
      cleanedRequest: {
        event: 'lead.created',
        delivery_id: 'abc123',
        delivered_at: '2026-05-03T10:00:00Z',
        data: { lead: sampleLead },
      },
    };
    const results = await appTester(App.triggers.new_lead.operation.perform, bundle);
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe(sampleLead.id);
    expect(results[0].delivery_id).toBe('abc123');
  });

  test('new_lead returns empty when the body has no lead', async () => {
    const bundle = { authData, cleanedRequest: { data: {} } };
    const results = await appTester(App.triggers.new_lead.operation.perform, bundle);
    expect(results).toEqual([]);
  });

  test('lead_status_changed surfaces from/to status', async () => {
    const bundle = {
      authData,
      cleanedRequest: {
        delivery_id: 'd9',
        data: {
          lead: sampleLead,
          from_status: 'new',
          to_status: 'contacted',
          actor_user_id: 7,
        },
      },
    };
    const results = await appTester(
      App.triggers.lead_status_changed.operation.perform,
      bundle,
    );
    expect(results).toHaveLength(1);
    expect(results[0].from_status).toBe('new');
    expect(results[0].to_status).toBe('contacted');
    expect(results[0].lead_id).toBe(sampleLead.id);
    // composite id keeps successive moves of the same lead distinct
    expect(results[0].id).toContain(sampleLead.id);
    expect(results[0].id).toContain('d9');
  });

  test('search_finished returns the search payload', async () => {
    const bundle = {
      authData,
      cleanedRequest: {
        delivery_id: 'srch1',
        data: { search: sampleSearch },
      },
    };
    const results = await appTester(
      App.triggers.search_finished.operation.perform,
      bundle,
    );
    expect(results).toHaveLength(1);
    expect(results[0].id).toBe(sampleSearch.id);
    expect(results[0].leads_count).toBe(47);
  });
});

describe('App definition is well-formed', () => {
  test('exposes the three documented triggers + tagsList helper', () => {
    expect(Object.keys(App.triggers).sort()).toEqual([
      'lead_status_changed',
      'new_lead',
      'search_finished',
      'tagsList',
    ]);
  });

  test('exposes the three documented creates', () => {
    expect(Object.keys(App.creates).sort()).toEqual([
      'add_lead_tag',
      'create_lead',
      'update_lead_status',
    ]);
  });

  test('every trigger we expose to users is a hook (not polling)', () => {
    for (const key of ['new_lead', 'lead_status_changed', 'search_finished']) {
      expect(App.triggers[key].operation.type).toBe('hook');
      expect(App.triggers[key].operation.performSubscribe).toBeDefined();
      expect(App.triggers[key].operation.performUnsubscribe).toBeDefined();
    }
  });
});
