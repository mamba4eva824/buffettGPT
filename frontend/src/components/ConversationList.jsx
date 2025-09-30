import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, Archive, Trash2, Edit2, Check, X, Hash, MoreHorizontal } from 'lucide-react';
import { DeleteConfirmationModal } from './DeleteConfirmationModal';

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
  const [openDropdownId, setOpenDropdownId] = useState(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [conversationToDelete, setConversationToDelete] = useState(null);
  const dropdownRef = useRef(null);

  // Filter conversations based on archive status
  const visibleConversations = conversations.filter(
    conv => showArchived ? conv.is_archived : !conv.is_archived
  );


  // Start editing a conversation title
  const startEdit = (conv) => {
    setEditingId(conv.conversation_id);
    setEditTitle(conv.title);
  };

  // Save edited title
  const saveEdit = async () => {
    const conversationBeingEdited = conversations.find(conv => conv.conversation_id === editingId);
    if (editTitle.trim() && editTitle !== conversationBeingEdited?.title) {
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

  // Toggle dropdown menu
  const toggleDropdown = (conversationId) => {
    setOpenDropdownId(openDropdownId === conversationId ? null : conversationId);
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setOpenDropdownId(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

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

  const handleDeleteConfirm = () => {
    if (conversationToDelete) {
      onDeleteConversation(conversationToDelete.conversation_id);
      setConversationToDelete(null);
    }
  };

  return (
    <>
      <DeleteConfirmationModal
        isOpen={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setConversationToDelete(null);
        }}
        onConfirm={handleDeleteConfirm}
        title="Delete Conversation"
        message="Are you sure you want to delete this conversation? This action cannot be undone."
        confirmText="Delete"
        cancelText="Cancel"
      />

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
                : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200'
            )}
          >
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
                    className="flex-1 rounded border border-indigo-300 dark:border-indigo-600 bg-white dark:bg-slate-700 px-2 py-1 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-500 dark:focus:border-indigo-400"
                    autoFocus
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      saveEdit();
                    }}
                    className="rounded p-1 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/20"
                  >
                    <Check className="h-3 w-3" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      cancelEdit();
                    }}
                    className="rounded p-1 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/20"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <>
                  <div className="truncate text-sm font-medium">
                    {conv.title || 'Untitled Conversation'}
                  </div>
                  {conv.message_count > 0 && (
                    <div className="mt-1 text-xs text-slate-500">
                      {conv.message_count} messages
                    </div>
                  )}
                </>
              )}
            </div>

            {/* 3-Dot Menu */}
            {!isEditing && (
              <div className="relative ml-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleDropdown(conv.conversation_id);
                  }}
                  className="rounded p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-600 hover:text-slate-600 dark:hover:text-slate-300 opacity-0 transition-opacity group-hover:opacity-100"
                  title="Options"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>

                {/* Dropdown Menu */}
                {openDropdownId === conv.conversation_id && (
                  <div
                    ref={dropdownRef}
                    className="absolute right-0 top-8 z-10 w-32 rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 py-1 shadow-lg"
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        startEdit(conv);
                        setOpenDropdownId(null);
                      }}
                      className="flex w-full items-center px-3 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-600"
                    >
                      <Edit2 className="mr-2 h-3 w-3" />
                      Edit
                    </button>
                    {!conv.is_archived && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onArchiveConversation(conv.conversation_id);
                          setOpenDropdownId(null);
                        }}
                        className="flex w-full items-center px-3 py-2 text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-600"
                      >
                        <Archive className="mr-2 h-3 w-3" />
                        Archive
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setConversationToDelete(conv);
                        setDeleteModalOpen(true);
                        setOpenDropdownId(null);
                      }}
                      className="flex w-full items-center px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                    >
                      <Trash2 className="mr-2 h-3 w-3" />
                      Delete
                    </button>
                  </div>
                )}
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
    </>
  );
}

export default ConversationList;