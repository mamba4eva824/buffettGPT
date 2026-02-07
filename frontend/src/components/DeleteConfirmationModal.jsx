import React from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle, X } from 'lucide-react';

/**
 * Delete Confirmation Modal Component
 * A reusable modal for confirming destructive actions
 * Uses React Portal to render at document root for proper layering
 */
export function DeleteConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title = "Delete Conversation",
  message = "Are you sure you want to delete this conversation? This action cannot be undone.",
  confirmText = "Delete",
  cancelText = "Cancel"
}) {
  if (!isOpen) return null;

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleConfirm = () => {
    onConfirm();
    onClose();
  };

  const modalContent = (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm transition-opacity duration-200"
      onClick={handleBackdropClick}
      style={{ pointerEvents: 'auto' }}
    >
      <div
        className="relative w-full max-w-md mx-4 bg-sand-50 dark:bg-warm-950 rounded-2xl shadow-2xl transform transition-all duration-200"
        onClick={(e) => e.stopPropagation()}
        style={{ pointerEvents: 'auto' }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-lg p-1 text-sand-400 hover:bg-sand-100 dark:hover:bg-warm-800 hover:text-sand-600 dark:hover:text-warm-200 transition-colors"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>

        {/* Content */}
        <div className="p-6">
          {/* Icon */}
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/20">
            <AlertTriangle className="h-6 w-6 text-red-600 dark:text-red-400" />
          </div>

          {/* Title */}
          <h3 className="text-lg font-semibold text-sand-900 dark:text-warm-50 mb-2">
            {title}
          </h3>

          {/* Message */}
          <p className="text-sm text-sand-600 dark:text-warm-300 mb-6">
            {message}
          </p>

          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="flex-1 rounded-xl border border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-900 px-4 py-2.5 text-sm font-medium text-sand-700 dark:text-warm-200 hover:bg-sand-50 dark:hover:bg-warm-700 transition-colors focus:outline-none focus:ring-2 focus:ring-sand-300 dark:focus:ring-warm-500 focus:ring-offset-2 dark:focus:ring-offset-warm-800"
            >
              {cancelText}
            </button>
            <button
              onClick={handleConfirm}
              className="flex-1 rounded-xl bg-red-600 dark:bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700 dark:hover:bg-red-700 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-warm-800 shadow-sm"
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  // Render modal at document root using portal
  return createPortal(modalContent, document.body);
}

export default DeleteConfirmationModal;