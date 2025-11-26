/**
 * Analysis API Client
 * Handles deep financial analysis requests for debt, cashflow, and valuation
 */

import logger from '../utils/logger';
import SSEClient from '../utils/sseClient';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';
const STREAMING_URL = import.meta.env.VITE_DEBT_ANALYSIS_STREAMING_URL || '';

/**
 * API Routes Configuration
 * Following RESTful conventions for financial analysis
 */
export const ANALYSIS_ENDPOINTS = {
  // Debt analysis using ML model (direct inference)
  DEBT: '/api/analyze/debt',

  // Conversational debt analysis via Bedrock Agent
  DEBT_CONVERSATIONAL: '/api/analyze/debt/conversational',

  // Future: Cashflow analysis
  CASHFLOW: '/api/analyze/cashflow',

  // Future: Valuation analysis
  VALUATION: '/api/analyze/valuation'
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

  try {
    const response = await fetch(url, {
      ...options,
      headers
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorMessage = `API Error (${response.status})`;

      try {
        const errorJson = JSON.parse(errorText);
        errorMessage = errorJson.error || errorJson.message || errorText;
      } catch {
        errorMessage = errorText || errorMessage;
      }

      throw new Error(errorMessage);
    }

    return response.json();
  } catch (error) {
    logger.error('Analysis API call failed:', error);
    throw error;
  }
}

/**
 * Validates ticker symbol format
 * @param {string} ticker - Stock ticker symbol
 * @returns {boolean} - True if valid ticker format
 */
export function validateTicker(ticker) {
  if (!ticker || typeof ticker !== 'string') {
    return false;
  }

  // Ticker should be 1-5 uppercase letters
  const tickerRegex = /^[A-Z]{1,5}$/;
  return tickerRegex.test(ticker.trim().toUpperCase());
}

/**
 * Analysis API Methods
 */
export const analysisApi = {
  /**
   * Analyze debt health for a company
   * POST /api/analyze/debt
   *
   * @param {string} ticker - Stock ticker symbol (e.g., 'AAPL', 'MSFT')
   * @param {number} fiscalYear - Optional fiscal year (defaults to current year)
   * @param {string} token - Optional authentication token
   * @returns {Promise<Object>} Analysis result with signal, confidence, and metrics
   */
  analyzeDebt: async (ticker, fiscalYear = null, token = null) => {
    // Validate ticker
    if (!validateTicker(ticker)) {
      throw new Error('Invalid ticker symbol. Please enter 1-5 uppercase letters (e.g., AAPL, MSFT, OKTA).');
    }

    const normalizedTicker = ticker.trim().toUpperCase();

    const requestBody = {
      ticker: normalizedTicker,
      ...(fiscalYear && { fiscal_year: fiscalYear })
    };

    logger.info(`Analyzing debt for ${normalizedTicker}`, requestBody);

    return apiCall(ANALYSIS_ENDPOINTS.DEBT, {
      method: 'POST',
      body: JSON.stringify(requestBody)
    }, token);
  },

  /**
   * Analyze debt health with conversational AI response
   * POST /api/analyze/debt/conversational
   *
   * @param {string} ticker - Stock ticker symbol (e.g., 'AAPL', 'MSFT')
   * @param {number} fiscalYear - Optional fiscal year (defaults to current year)
   * @param {string} sessionId - Optional session ID for follow-up questions
   * @param {string} token - Optional authentication token
   * @param {string} connectionId - Optional WebSocket connection ID for streaming
   * @returns {Promise<Object>} Conversational analysis with embedded metrics
   */
  analyzeDebtConversational: async (ticker, fiscalYear = null, sessionId = null, token = null, connectionId = null) => {
    // Validate ticker
    if (!validateTicker(ticker)) {
      throw new Error('Invalid ticker symbol. Please enter 1-5 uppercase letters (e.g., AAPL, MSFT, OKTA).');
    }

    const normalizedTicker = ticker.trim().toUpperCase();

    const requestBody = {
      ticker: normalizedTicker,
      ...(fiscalYear && { fiscal_year: fiscalYear }),
      ...(sessionId && { session_id: sessionId }),
      ...(connectionId && { connection_id: connectionId })
    };

    // Log connection status for debugging
    if (connectionId) {
      logger.info(`✅ Requesting conversational debt analysis with WebSocket streaming for ${normalizedTicker}`, {
        ...requestBody,
        streamingEnabled: true
      });
    } else {
      logger.warn(`⚠️ Requesting conversational debt analysis WITHOUT WebSocket streaming for ${normalizedTicker}`, {
        ...requestBody,
        streamingEnabled: false,
        note: 'Response will not stream in real-time'
      });
    }

    logger.info(`Requesting conversational debt analysis for ${normalizedTicker}`, requestBody);

    return apiCall(ANALYSIS_ENDPOINTS.DEBT_CONVERSATIONAL, {
      method: 'POST',
      body: JSON.stringify(requestBody)
    }, token);
  },

  /**
   * Analyze debt health with real-time SSE streaming
   * Uses Lambda Function URL with response streaming for true real-time experience
   *
   * @param {string} ticker - Stock ticker symbol (e.g., 'AAPL', 'MSFT')
   * @param {number} fiscalYear - Optional fiscal year
   * @param {string} sessionId - Optional session ID for follow-up questions
   * @param {string} token - Optional authentication token
   * @param {Object} callbacks - { onChunk, onComplete, onError, onConnected }
   * @returns {SSEClient} SSE client instance for cancellation
   */
  analyzeDebtConversationalStreaming: (ticker, fiscalYear = null, sessionId = null, token = null, callbacks = {}) => {
    // Validate ticker
    if (!validateTicker(ticker)) {
      throw new Error('Invalid ticker symbol. Please enter 1-5 uppercase letters (e.g., AAPL, MSFT, OKTA).');
    }

    // Check if streaming URL is configured
    if (!STREAMING_URL) {
      logger.error('Streaming URL not configured');
      throw new Error('SSE streaming is not configured. Please set VITE_DEBT_ANALYSIS_STREAMING_URL environment variable.');
    }

    const normalizedTicker = ticker.trim().toUpperCase();

    const requestBody = {
      ticker: normalizedTicker,
      ...(fiscalYear && { fiscal_year: fiscalYear }),
      ...(sessionId && { session_id: sessionId })
    };

    logger.info(`🌊 Starting SSE streaming analysis for ${normalizedTicker}`, {
      ...requestBody,
      streamingUrl: STREAMING_URL
    });

    // Create and start SSE client
    const client = new SSEClient(STREAMING_URL, { token });

    client.stream(requestBody, callbacks).catch(error => {
      logger.error('SSE streaming failed:', error);
      if (callbacks.onError) callbacks.onError(error);
    });

    return client; // Return for cancellation
  },

  /**
   * Future: Analyze cashflow health for a company
   * POST /api/analyze/cashflow
   */
  analyzeCashflow: async (ticker, fiscalYear = null, token = null) => {
    throw new Error('Cashflow analysis is not yet implemented');
  },

  /**
   * Future: Analyze valuation for a company
   * POST /api/analyze/valuation
   */
  analyzeValuation: async (ticker, fiscalYear = null, token = null) => {
    throw new Error('Valuation analysis is not yet implemented');
  }
};

/**
 * Helper function to format analysis response for display
 * @param {Object} response - API response
 * @returns {Object} Formatted analysis data
 */
export function formatAnalysisResponse(response) {
  const { signal, confidence, analysis, metrics, ticker, fiscal_year } = response;

  return {
    type: 'debt_analysis',
    ticker: ticker?.toUpperCase(),
    fiscalYear: fiscal_year,
    signal: {
      value: signal,
      label: getSignalLabel(signal),
      color: getSignalColor(signal)
    },
    confidence: {
      value: confidence,
      percentage: (confidence * 100).toFixed(1)
    },
    analysis,
    metrics,
    timestamp: new Date().toISOString()
  };
}

/**
 * Get human-readable label for signal value
 */
function getSignalLabel(signal) {
  const labels = {
    '-2': 'VERY WEAK',
    '-1': 'WEAK',
    '0': 'NEUTRAL',
    '1': 'STRONG',
    '2': 'VERY STRONG'
  };
  return labels[signal?.toString()] || 'UNKNOWN';
}

/**
 * Get color code for signal value
 */
function getSignalColor(signal) {
  const colors = {
    '-2': 'red',     // Very Weak
    '-1': 'orange',  // Weak
    '0': 'gray',     // Neutral
    '1': 'green',    // Strong
    '2': 'emerald'   // Very Strong
  };
  return colors[signal?.toString()] || 'gray';
}

export default analysisApi;
