import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

export async function fetchRecentEarnings(limit = 50) {
  const url = `${API_BASE_URL}/earnings/recent?limit=${limit}`;
  logger.info('Fetching recent earnings');

  const response = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }

  return response.json();
}

export async function fetchUpcomingEarnings(limit = 50) {
  const url = `${API_BASE_URL}/earnings/upcoming?limit=${limit}`;
  logger.info('Fetching upcoming earnings');

  const response = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }

  return response.json();
}

export async function fetchSeasonOverview() {
  const url = `${API_BASE_URL}/earnings/season`;
  logger.info('Fetching earnings season overview');

  const response = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }

  return response.json();
}
