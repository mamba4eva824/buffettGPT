import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

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

export async function fetchWatchlist(token) {
  logger.info('Fetching watchlist');
  return apiCall('/watchlist', { method: 'GET' }, token);
}

export async function addToWatchlist(ticker, token) {
  logger.info(`Adding ${ticker} to watchlist`);
  return apiCall(`/watchlist/${ticker}`, { method: 'PUT' }, token);
}

export async function removeFromWatchlist(ticker, token) {
  logger.info(`Removing ${ticker} from watchlist`);
  return apiCall(`/watchlist/${ticker}`, { method: 'DELETE' }, token);
}
