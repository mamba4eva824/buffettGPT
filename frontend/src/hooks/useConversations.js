import { useState, useEffect, useCallback } from 'react';
import logger from '../utils/logger';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

/**
 * Custom hook for managing conversations with the conversations API
 */
export function useConversations({ token, userId, includeArchived = false }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [nextCursor, setNextCursor] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Fetch conversations from API (first page or with cursor for subsequent pages)
  const fetchConversations = useCallback(async (cursor = null) => {
    if (!token || !userId || !API_BASE_URL) {
      logger.log('Skipping conversation fetch - missing requirements', { hasToken: !!token, hasUserId: !!userId, hasUrl: !!API_BASE_URL });
      return;
    }

    if (cursor) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const url = new URL(`${API_BASE_URL}/conversations`);
      if (includeArchived) {
        url.searchParams.set('include_archived', 'true');
      }
      if (cursor) {
        url.searchParams.set('cursor', cursor);
      }

      const response = await fetch(url.toString(), {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch conversations: ${response.status}`);
      }

      const data = await response.json();
      const conversationsList = data.conversations || [];

      // Sort by updated_at (most recent first) - ISO strings
      conversationsList.sort((a, b) => {
        const dateA = new Date(a.updated_at || 0);
        const dateB = new Date(b.updated_at || 0);
        return dateB - dateA;
      });

      if (cursor) {
        // Append to existing conversations for "load more"
        setConversations(prev => [...prev, ...conversationsList]);
      } else {
        setConversations(conversationsList);
      }

      // Store pagination cursor for next page
      setNextCursor(data.next_cursor || null);
    } catch (err) {
      logger.error('Error fetching conversations:', err);
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [token, userId, includeArchived]);

  // Load more conversations using the pagination cursor
  const loadMoreConversations = useCallback(async () => {
    if (nextCursor && !loadingMore) {
      await fetchConversations(nextCursor);
    }
  }, [nextCursor, loadingMore, fetchConversations]);

  // Create a new conversation
  const createConversation = useCallback(async (title = 'New Conversation') => {
    if (!token || !userId || !API_BASE_URL) {
      logger.error('Cannot create conversation - missing auth or API URL');
      return null;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/conversations`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title,
          user_id: userId
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to create conversation: ${response.status}`);
      }

      const newConversation = await response.json();

      // Add to local state
      setConversations(prev => [newConversation, ...prev]);
      setSelectedConversation(newConversation);

      return newConversation;
    } catch (err) {
      logger.error('Error creating conversation:', err);
      setError(err.message);
      return null;
    }
  }, [token, userId]);

  // Update conversation (title, archive status, etc.)
  const updateConversation = useCallback(async (conversationId, updates) => {
    if (!token || !API_BASE_URL) {
      logger.error('Cannot update conversation - missing auth or API URL');
      return false;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });

      if (!response.ok) {
        throw new Error(`Failed to update conversation: ${response.status}`);
      }

      await response.json();

      // Merge updates into local state (API returns success message, not full object)
      setConversations(prev =>
        prev.map(conv =>
          conv.conversation_id === conversationId ? { ...conv, ...updates } : conv
        )
      );

      // Update selected if it's the current one
      if (selectedConversation?.conversation_id === conversationId) {
        setSelectedConversation(prev => ({ ...prev, ...updates }));
      }

      return true;
    } catch (err) {
      logger.error('Error updating conversation:', err);
      setError(err.message);
      return false;
    }
  }, [token, selectedConversation]);

  // Archive a conversation
  const archiveConversation = useCallback(async (conversationId) => {
    return updateConversation(conversationId, { is_archived: true });
  }, [updateConversation]);

  // Delete a conversation
  const deleteConversation = useCallback(async (conversationId) => {
    if (!token || !API_BASE_URL) {
      logger.error('Cannot delete conversation - missing auth or API URL');
      return false;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to delete conversation: ${response.status}`);
      }

      // Remove from local state
      setConversations(prev => prev.filter(conv => conv.conversation_id !== conversationId));

      // Clear selection if it's the deleted one
      if (selectedConversation?.conversation_id === conversationId) {
        setSelectedConversation(null);
      }

      return true;
    } catch (err) {
      logger.error('Error deleting conversation:', err);
      setError(err.message);
      return false;
    }
  }, [token, selectedConversation]);

  // Auto-fetch conversations when auth changes or includeArchived changes
  useEffect(() => {
    if (token && userId) {
      fetchConversations();
    } else {
      // Clear conversations if user logs out
      setConversations([]);
      setSelectedConversation(null);
    }
  }, [token, userId, includeArchived, fetchConversations]);

  return {
    conversations,
    loading,
    error,
    selectedConversation,
    setSelectedConversation,
    fetchConversations,
    loadMoreConversations,
    loadingMore,
    hasMore: !!nextCursor,
    createConversation,
    updateConversation,
    archiveConversation,
    deleteConversation
  };
}