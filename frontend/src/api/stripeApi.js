/**
 * Stripe API Client
 * Handles subscription management API calls
 */

import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

/**
 * Stripe/Subscription API Routes
 */
export const STRIPE_ENDPOINTS = {
  // Create Stripe Checkout session for Plus upgrade
  CHECKOUT: '/subscription/checkout',

  // Create Stripe Customer Portal session
  PORTAL: '/subscription/portal',

  // Get current subscription status
  STATUS: '/subscription/status',
};

/**
 * Helper function to make authenticated API calls
 */
async function apiCall(endpoint, options = {}, token = null) {
  const url = `${API_BASE_URL}${endpoint}`;

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers
  });

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
 * Stripe API Methods
 */
export const stripeApi = {
  /**
   * Create a Stripe Checkout session for Plus subscription
   * POST /subscription/checkout
   *
   * @param {string} token - JWT auth token
   * @param {object} options - Optional success/cancel URLs
   * @returns {Promise<{checkout_url: string}>}
   */
  createCheckoutSession: async (token, options = {}) => {
    const { successUrl, cancelUrl } = options;

    const body = {};
    if (successUrl) body.success_url = successUrl;
    if (cancelUrl) body.cancel_url = cancelUrl;

    logger.info('Creating checkout session');

    const result = await apiCall(STRIPE_ENDPOINTS.CHECKOUT, {
      method: 'POST',
      body: JSON.stringify(body)
    }, token);

    logger.info('Checkout session created');
    return result;
  },

  /**
   * Create a Stripe Customer Portal session
   * POST /subscription/portal
   *
   * @param {string} token - JWT auth token
   * @returns {Promise<{portal_url: string}>}
   */
  createPortalSession: async (token) => {
    logger.info('Creating portal session');

    const result = await apiCall(STRIPE_ENDPOINTS.PORTAL, {
      method: 'POST',
      body: JSON.stringify({})
    }, token);

    logger.info('Portal session created');
    return result;
  },

  /**
   * Get current subscription status
   * GET /subscription/status
   *
   * @param {string} token - JWT auth token
   * @returns {Promise<{
   *   subscription_tier: 'free' | 'plus',
   *   subscription_status: string | null,
   *   token_limit: number,
   *   has_subscription: boolean,
   *   cancel_at_period_end: boolean,
   *   billing_day: number | null,
   *   current_period_end: number | null
   * }>}
   */
  getSubscriptionStatus: async (token) => {
    logger.info('Fetching subscription status');

    const result = await apiCall(STRIPE_ENDPOINTS.STATUS, {
      method: 'GET'
    }, token);

    return result;
  },

  /**
   * Redirect to Stripe Checkout
   * Creates session and redirects user
   *
   * @param {string} token - JWT auth token
   * @param {object} options - Optional success/cancel URLs
   */
  redirectToCheckout: async (token, options = {}) => {
    const result = await stripeApi.createCheckoutSession(token, options);

    if (result.checkout_url) {
      window.location.href = result.checkout_url;
    } else {
      throw new Error('No checkout URL returned');
    }
  },

  /**
   * Redirect to Stripe Customer Portal
   * Creates session and redirects user
   *
   * @param {string} token - JWT auth token
   */
  redirectToPortal: async (token) => {
    const result = await stripeApi.createPortalSession(token);

    if (result.portal_url) {
      window.location.href = result.portal_url;
    } else {
      throw new Error('No portal URL returned');
    }
  }
};

export default stripeApi;
