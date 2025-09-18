import React, { useState } from 'react';
import { MessageSquare, Archive, Trash2, Edit2, Check, X, Clock, Hash } from 'lucide-react';

function classNames(...classes) {
  return classes.filter(Boolean).join(' ');
}

/**
 * Conversation List Component
 * Displays a list of conversations with management actions
 */
export function ConversationList({
  conversations = [],
  selectedConversation,
  onSelectConversation,
  onUpdateConversation,
  onArchiveConversation,
  onDeleteConversation,
  showArchived = false,
  loading = false
}) {
  const [editingId, setEditingId] = useState(null);
  const [editTitle, setEditTitle] = useState('');

  // Filter conversations based on archive status
  const visibleConversations = conversations.filter(
    conv => showArchived ? conv.is_archived : !conv.is_archived
  );

  // Format timestamp for display
  const formatTime = (timestamp) => {
    if (!timestamp) return 'Never';

    const date = new Date(timestamp * 1000); // Convert Unix timestamp to JS Date
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  // Start editing a conversation title
  const startEdit = (conv) => {
    setEditingId(conv.conversation_id);
    setEditTitle(conv.title);
  };

  // Save edited title
  const saveEdit = async () => {
    if (editTitle.trim() && editTitle !== selectedConversation?.title) {
      await onUpdateConversation(editingId, { title: editTitle.trim() });
    }
    setEditingId(null);
    setEditTitle('');
  };

  // Cancel editing
  const cancelEdit = () => {
    setEditingId(null);
    setEditTitle('');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-sm text-slate-400">Loading conversations...</div>
      </div>
    );
  }

  if (visibleConversations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 p-4 text-center">
        <MessageSquare className="mx-auto h-8 w-8 text-slate-300" />
        <div className="mt-2 text-sm text-slate-500">
          {showArchived ? 'No archived conversations' : 'No conversations yet'}
        </div>
        {!showArchived && (
          <div className="mt-1 text-xs text-slate-400">
            Start a new chat to create your first conversation
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {visibleConversations.map((conv) => {
        const isSelected = selectedConversation?.conversation_id === conv.conversation_id;
        const isEditing = editingId === conv.conversation_id;

        return (
          <div
            key={conv.conversation_id}
            className={classNames(
              'group relative flex items-center rounded-lg px-3 py-2 transition-colors',
              isSelected
                ? 'bg-indigo-50 text-indigo-700'
                : 'hover:bg-slate-50 text-slate-700'
            )}
          >
            {/* Conversation Icon */}
            <MessageSquare className="mr-3 h-4 w-4 flex-shrink-0 text-slate-400" />

            {/* Conversation Details */}
            <div
              className="min-w-0 flex-1 cursor-pointer"
              onClick={() => !isEditing && onSelectConversation(conv)}
            >
              {isEditing ? (
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit();
                      if (e.key === 'Escape') cancelEdit();
                    }}
                    className="flex-1 rounded border border-indigo-300 bg-white px-2 py-1 text-sm outline-none focus:border-indigo-500"
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      saveEdit();
                    }}
                    className="rounded p-1 text-green-600 hover:bg-green-50"
                  >
                    <Check className="h-3 w-3" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      cancelEdit();
                    }}
                    className="rounded p-1 text-red-600 hover:bg-red-50"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <>
                  <div className="truncate text-sm font-medium">
                    {conv.title || 'Untitled Conversation'}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                    <Clock className="h-3 w-3" />
                    <span>{formatTime(conv.updated_at)}</span>
                    {conv.message_count > 0 && (
                      <>
                        <span>•</span>
                        <span>{conv.message_count} messages</span>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* Action Buttons */}
            {!isEditing && (
              <div className="ml-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    startEdit(conv);
                  }}
                  className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                  title="Rename"
                >
                  <Edit2 className="h-3 w-3" />
                </button>
                {!conv.is_archived && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onArchiveConversation(conv.conversation_id);
                    }}
                    className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    title="Archive"
                  >
                    <Archive className="h-3 w-3" />
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm('Delete this conversation? This cannot be undone.')) {
                      onDeleteConversation(conv.conversation_id);
                    }
                  }}
                  className="rounded p-1 text-red-400 hover:bg-red-50 hover:text-red-600"
                  title="Delete"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            )}

            {/* Selected Indicator */}
            {isSelected && (
              <div className="absolute inset-y-0 left-0 w-1 rounded-r bg-indigo-600" />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default ConversationList;