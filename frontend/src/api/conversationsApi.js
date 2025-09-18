/**
 * Conversations API Client
 * Handles all CRUD operations for conversations
 */

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

/**
 * API Routes Configuration
 * Following RESTful conventions for conversation management
 */
export const CONVERSATION_ENDPOINTS = {
  // List all conversations for a user
  LIST: '/conversations',

  // Get specific conversation with messages
  GET: (conversationId) => `/conversations/${conversationId}`,

  // Create new conversation
  CREATE: '/conversations',

  // Update conversation (title, archive status)
  UPDATE: (conversationId) => `/conversations/${conversationId}`,

  // Delete conversation
  DELETE: (conversationId) => `/conversations/${conversationId}`,

  // Get messages for a conversation
  MESSAGES: (conversationId) => `/conversations/${conversationId}/messages`
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
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }

  return response.json();
}

/**
 * Conversations API Methods
 */
export const conversationsApi = {
  /**
   * List all conversations for the authenticated user
   * GET /conversations
   */
  list: async (token) => {
    return apiCall(CONVERSATION_ENDPOINTS.LIST, { method: 'GET' }, token);
  },

  /**
   * Get a specific conversation with its messages
   * GET /conversations/:id
   */
  get: async (conversationId, token) => {
    return apiCall(CONVERSATION_ENDPOINTS.GET(conversationId), { method: 'GET' }, token);
  },

  /**
   * Create a new conversation
   * POST /conversations
   */
  create: async (data, token) => {
    return apiCall(CONVERSATION_ENDPOINTS.CREATE, {
      method: 'POST',
      body: JSON.stringify(data)
    }, token);
  },

  /**
   * Update a conversation (title, archive status, etc.)
   * PUT /conversations/:id
   */
  update: async (conversationId, data, token) => {
    return apiCall(CONVERSATION_ENDPOINTS.UPDATE(conversationId), {
      method: 'PUT',
      body: JSON.stringify(data)
    }, token);
  },

  /**
   * Delete a conversation
   * DELETE /conversations/:id
   */
  delete: async (conversationId, token) => {
    return apiCall(CONVERSATION_ENDPOINTS.DELETE(conversationId), {
      method: 'DELETE'
    }, token);
  },

  /**
   * Get messages for a conversation
   * GET /conversations/:id/messages
   */
  getMessages: async (conversationId, token, limit = 100) => {
    const endpoint = `${CONVERSATION_ENDPOINTS.MESSAGES(conversationId)}?limit=${limit}`;
    return apiCall(endpoint, { method: 'GET' }, token);
  }
};

/**
 * Helper function to fetch conversation history
 * This can be used to load messages when switching conversations
 */
export async function loadConversationHistory(conversationId, token) {
  try {
    // First get the conversation details
    const conversation = await conversationsApi.get(conversationId, token);

    // Then get the messages
    const messages = await conversationsApi.getMessages(conversationId, token);

    return {
      conversation,
      messages: messages.messages || []
    };
  } catch (error) {
    console.error('Error loading conversation history:', error);
    throw error;
  }
}

export default conversationsApi;