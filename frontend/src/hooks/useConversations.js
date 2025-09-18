import { useState, useEffect, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_REST_API_URL || '';

/**
 * Custom hook for managing conversations with the conversations API
 */
export function useConversations({ token, userId }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedConversation, setSelectedConversation] = useState(null);

  // Fetch conversations from API
  const fetchConversations = useCallback(async () => {
    if (!token || !userId || !API_BASE_URL) {
      console.log('Skipping conversation fetch - missing requirements', { hasToken: !!token, hasUserId: !!userId, hasUrl: !!API_BASE_URL });
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/conversations`, {
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

      // Sort by updated_at (most recent first)
      conversationsList.sort((a, b) => b.updated_at - a.updated_at);

      setConversations(conversationsList);
    } catch (err) {
      console.error('Error fetching conversations:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, userId]);

  // Create a new conversation
  const createConversation = useCallback(async (title = 'New Conversation') => {
    if (!token || !userId || !API_BASE_URL) {
      console.error('Cannot create conversation - missing auth or API URL');
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
      console.error('Error creating conversation:', err);
      setError(err.message);
      return null;
    }
  }, [token, userId]);

  // Update conversation (title, archive status, etc.)
  const updateConversation = useCallback(async (conversationId, updates) => {
    if (!token || !API_BASE_URL) {
      console.error('Cannot update conversation - missing auth or API URL');
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

      const updatedConversation = await response.json();

      // Update local state
      setConversations(prev =>
        prev.map(conv =>
          conv.conversation_id === conversationId ? updatedConversation : conv
        )
      );

      // Update selected if it's the current one
      if (selectedConversation?.conversation_id === conversationId) {
        setSelectedConversation(updatedConversation);
      }

      return true;
    } catch (err) {
      console.error('Error updating conversation:', err);
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
      console.error('Cannot delete conversation - missing auth or API URL');
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
      console.error('Error deleting conversation:', err);
      setError(err.message);
      return false;
    }
  }, [token, selectedConversation]);

  // Auto-fetch conversations when auth changes
  useEffect(() => {
    if (token && userId) {
      fetchConversations();
    } else {
      // Clear conversations if user logs out
      setConversations([]);
      setSelectedConversation(null);
    }
  }, [token, userId, fetchConversations]);

  return {
    conversations,
    loading,
    error,
    selectedConversation,
    setSelectedConversation,
    fetchConversations,
    createConversation,
    updateConversation,
    archiveConversation,
    deleteConversation
  };
}