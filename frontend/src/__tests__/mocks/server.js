/**
 * MSW Server Setup
 *
 * Creates a mock server for testing SSE streams and API endpoints.
 */
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

// Create the server with default handlers
export const server = setupServer(...handlers);
