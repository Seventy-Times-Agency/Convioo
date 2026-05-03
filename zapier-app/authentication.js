'use strict';

// Custom auth: user pastes an API key issued from Settings → Безопасность → API.
// The backend accepts it via `Authorization: Bearer <token>` and resolves to
// the issuing user. The optional `apiUrl` lets self-hosted / staging users
// point the integration at a non-production deployment.

const DEFAULT_API_URL = 'https://api.convioo.com';

const test = async (z, bundle) => {
  // GET /api/v1/auth/me returns the authenticated user, so a 200 here
  // confirms the API key works. Bearer auth was wired across the API in
  // the public-API milestone (see auth.py:_resolve_api_key).
  const response = await z.request({
    url: '{{bundle.authData.apiUrl}}/api/v1/auth/me',
    method: 'GET',
  });
  return response.data;
};

module.exports = {
  type: 'custom',
  test,
  fields: [
    {
      key: 'apiKey',
      label: 'API key',
      type: 'password',
      required: true,
      helpText:
        'Issue from Convioo → Settings → Безопасность → API keys. ' +
        'Treat it like a password — it grants full access to your CRM.',
    },
    {
      key: 'apiUrl',
      label: 'API base URL',
      type: 'string',
      required: false,
      default: DEFAULT_API_URL,
      helpText:
        'Override only if you self-host Convioo. Leave the default for ' +
        'app.convioo.com.',
    },
  ],
  connectionLabel: '{{bundle.authData.email}}',
};
