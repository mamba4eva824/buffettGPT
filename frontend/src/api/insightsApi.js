import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

export async function fetchInsights(ticker) {
  const url = `${API_BASE_URL}/insights/${encodeURIComponent(ticker)}`;

  logger.info(`Fetching insights for ${ticker}`);

  const response = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!response.ok) {
    const errorText = await response.text();
    let errorData;
    try {
      errorData = JSON.parse(errorText);
    } catch {
      errorData = { error: errorText };
    }
    throw new Error(errorData.error || `API Error (${response.status})`);
  }

  return response.json();
}
