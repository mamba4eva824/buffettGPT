/**
 * Waitlist API Client
 * Handles waitlist signup and referral tracking API calls
 */

import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

/**
 * Waitlist API Routes
 */
export const WAITLIST_ENDPOINTS = {
  SIGNUP: '/waitlist/signup',
  STATUS: '/waitlist/status',
};

/**
 * Helper function to make API calls (no auth required)
 */
async function apiCall(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };

  const response = await fetch(url, {
    ...options,
    headers
  });

  // Handle 409 (already registered) specially — still has useful data
  if (response.status === 409) {
    const data = await response.json();
    return { ...data, alreadyRegistered: true };
  }

  if (!response.ok) {
    const errorText = await response.text();
    let errorData;
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { error: errorText };
    }
    throw new Error(errorData.message || errorData.error || `API Error (${response.status})`);
  }

  return response.json();
}

/**
 * Waitlist API Methods
 */
export const waitlistApi = {
  /**
   * Sign up for the waitlist
   * POST /waitlist/signup
   *
   * @param {string} email - User email address
   * @param {string|null} referralCode - Optional referral code from referrer
   * @returns {Promise<{email, referral_code, position, referral_count, status, tiers}>}
   */
  signup: async (email, referralCode = null) => {
    logger.info('Signing up for waitlist');

    const body = { email };
    if (referralCode) body.referral_code = referralCode;

    const result = await apiCall(WAITLIST_ENDPOINTS.SIGNUP, {
      method: 'POST',
      body: JSON.stringify(body),
    });

    logger.info('Waitlist signup complete');
    return result;
  },

  /**
   * Get waitlist status and referral dashboard
   * GET /waitlist/status?email=...&code=...
   *
   * @param {string} email - User email address
   * @param {string} code - User's own referral code (lightweight auth)
   * @returns {Promise<{email, referral_code, position, referral_count, status, current_tier, next_tier, tiers}>}
   */
  getStatus: async (email, code) => {
    logger.info('Fetching waitlist status');

    const params = new URLSearchParams({ email, code });
    const result = await apiCall(`${WAITLIST_ENDPOINTS.STATUS}?${params}`, {
      method: 'GET',
    });

    return result;
  },
};

export default waitlistApi;
