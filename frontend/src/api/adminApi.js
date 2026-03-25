import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';
const USE_MOCK = true;

const MOCK_SETTINGS = {
  token_limits: {
    plus: 2000000,
    free: 100000,
    default_fallback: 100000,
    followup_access: {
      anonymous: 0,
      free: 0,
      plus: 1000000,
    },
  },
  rate_limits: {
    anonymous_monthly: 5,
    authenticated_monthly: 500,
    grace_period_hours: 1,
    tiered: {
      anonymous: { daily: 5, hourly: 2, per_minute: 1, burst: 1, session_ttl_hours: 24 },
      authenticated: { daily: 50, hourly: 20, per_minute: 5, burst: 3, session_ttl_hours: 24 },
      premium: { daily: 200, hourly: 60, per_minute: 15, burst: 10, session_ttl_hours: 48 },
      enterprise: { daily: 1000, hourly: 200, per_minute: 50, burst: 25, session_ttl_hours: 72 },
    },
  },
  model_config: {
    followup_temperature: 0.7,
    followup_max_tokens: 2048,
    market_intel_temperature: 0.3,
    market_intel_max_tokens: 2048,
    max_orchestration_turns: 10,
  },
  feature_flags: {
    enable_rate_limiting: true,
    enable_device_fingerprinting: true,
  },
  notification_thresholds: {
    warning_percent: 80,
    critical_percent: 90,
  },
  referral_tiers: [
    { threshold: 5, trial_days: 90 },
    { threshold: 3, trial_days: 30 },
  ],
};

// Deep clone to avoid mutation between calls
const cloneMock = () => JSON.parse(JSON.stringify(MOCK_SETTINGS));

let mockState = cloneMock();

async function apiCall(endpoint, options = {}, token = null) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }

  return response.json();
}

export const adminApi = {
  getSettings: async (token) => {
    if (USE_MOCK) {
      logger.log('[AdminAPI] Returning mock settings');
      await new Promise((r) => setTimeout(r, 300));
      return { settings: JSON.parse(JSON.stringify(mockState)) };
    }
    return apiCall('/admin/settings', { method: 'GET' }, token);
  },

  updateSettings: async (token, category, values) => {
    if (USE_MOCK) {
      logger.log('[AdminAPI] Mock update:', category, values);
      await new Promise((r) => setTimeout(r, 400));
      if (mockState[category]) {
        mockState[category] = { ...mockState[category], ...values };
      }
      return { success: true, category, updated: mockState[category] };
    }
    return apiCall(`/admin/settings/${category}`, {
      method: 'PUT',
      body: JSON.stringify(values),
    }, token);
  },

  resetMock: () => {
    mockState = cloneMock();
  },
};

export default adminApi;
