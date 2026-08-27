'use strict';

// Inject Authorization: Bearer + a sane default base URL on every request.
// The REST-hook subscribe/unsubscribe calls and every create action go
// through this, so callers never have to remember the header.

const DEFAULT_API_URL = 'https://api.convioo.com';

const includeBearer = (request, z, bundle) => {
  if (bundle.authData && bundle.authData.apiKey) {
    request.headers = request.headers || {};
    request.headers.Authorization = `Bearer ${bundle.authData.apiKey}`;
  }
  if (request.url && request.url.startsWith('/')) {
    const base =
      (bundle.authData && bundle.authData.apiUrl) || DEFAULT_API_URL;
    request.url = `${base.replace(/\/$/, '')}${request.url}`;
  }
  return request;
};

const handleHttpErrors = (response, z) => {
  if (response.status === 401 || response.status === 403) {
    throw new z.errors.RefreshAuthError(
      'API key was rejected. Re-authenticate in Convioo settings.',
    );
  }
  if (response.status >= 400) {
    let detail;
    try {
      detail = JSON.parse(response.content).detail;
    } catch (_e) {
      detail = response.content;
    }
    throw new z.errors.Error(
      `Convioo API ${response.status}: ${detail || 'unknown error'}`,
      'ApiError',
      response.status,
    );
  }
  return response;
};

module.exports = { includeBearer, handleHttpErrors };
