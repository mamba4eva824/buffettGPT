import React, { useState, useEffect } from 'react';
import { User } from 'lucide-react';

/**
 * Robust Avatar component with fallback handling and error recovery
 * Handles Google OAuth profile pictures and provides fallbacks for failed loads
 */
export function Avatar({
  src,
  alt = "User avatar",
  size = "w-8 h-8",
  className = "",
  fallbackIcon = User,
  showInitials = true
}) {
  const [imageError, setImageError] = useState(false);
  const [imageLoading, setImageLoading] = useState(!!src);
  const [actualSrc, setActualSrc] = useState(src);
  const [retryCount, setRetryCount] = useState(0);
  const [hasTriedCleanUrl, setHasTriedCleanUrl] = useState(false);

  // Reset error state when src changes
  useEffect(() => {
    if (src && src !== actualSrc) {
      setImageError(false);
      setImageLoading(!!src);
      setActualSrc(src);
      setRetryCount(0);
      setHasTriedCleanUrl(false);
    }
  }, [src]);

  // Handle image load error with improved retry logic
  const handleImageError = () => {
    console.warn('Avatar image failed to load:', actualSrc);
    setImageLoading(false);

    // Try to fix common Google Photos URL issues (only once)
    if (!hasTriedCleanUrl && actualSrc && actualSrc.includes('googleusercontent.com') && retryCount === 0) {
      let cleanUrl = actualSrc;

      // Remove size parameters like =s96-c
      if (actualSrc.includes('=s') || actualSrc.includes('=w') || actualSrc.includes('=h')) {
        cleanUrl = actualSrc.split('=')[0];
      }

      // Try without any query parameters
      if (cleanUrl === actualSrc && actualSrc.includes('?')) {
        cleanUrl = actualSrc.split('?')[0];
      }

      if (cleanUrl !== actualSrc) {
        console.log('Retrying with cleaned URL:', cleanUrl);
        setActualSrc(cleanUrl);
        setImageError(false);
        setImageLoading(true);
        setRetryCount(1);
        setHasTriedCleanUrl(true);
        return;
      }
    }

    // If we've tried everything or it's not a Google URL, show fallback
    setImageError(true);
  };

  // Handle successful image load
  const handleImageLoad = () => {
    setImageLoading(false);
    setImageError(false);
  };

  // Extract initials from alt text for fallback
  const getInitials = (name) => {
    if (!name || !showInitials) return '';

    // Clean the name and extract initials
    const cleanName = name.trim();
    if (!cleanName) return '';

    const words = cleanName.split(/\s+/).filter(word => word.length > 0);
    if (words.length === 0) return '';

    // Get first letter of first word and first letter of last word (if different)
    const firstInitial = words[0].charAt(0).toUpperCase();
    const lastInitial = words.length > 1 ? words[words.length - 1].charAt(0).toUpperCase() : '';

    return firstInitial + lastInitial;
  };

  // Generate a consistent color based on the name
  const getBackgroundColor = (name) => {
    if (!name) return 'bg-sand-200 dark:bg-warm-800';

    // Simple hash function for consistent colors
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }

    const colors = [
      'bg-red-100 dark:bg-red-800',
      'bg-blue-100 dark:bg-blue-800',
      'bg-green-100 dark:bg-green-800',
      'bg-yellow-100 dark:bg-yellow-800',
      'bg-purple-100 dark:bg-purple-800',
      'bg-pink-100 dark:bg-pink-800',
      'bg-indigo-100 dark:bg-indigo-800',
      'bg-teal-100 dark:bg-teal-800',
    ];

    return colors[Math.abs(hash) % colors.length];
  };

  const FallbackIcon = fallbackIcon;
  const initials = getInitials(alt);
  const backgroundColor = getBackgroundColor(alt);

  // Show fallback if no src, error occurred, or still loading and no valid src
  if (!actualSrc || imageError || (imageLoading && !actualSrc)) {
    return (
      <div className={`${size} ${backgroundColor} rounded-full flex items-center justify-center ${className}`}>
        {initials && initials.length > 0 ? (
          <span className="text-xs font-semibold text-sand-700 dark:text-warm-100 select-none">
            {initials}
          </span>
        ) : (
          <FallbackIcon className="h-1/2 w-1/2 text-sand-500 dark:text-warm-300" />
        )}
      </div>
    );
  }

  return (
    <div className={`${size} rounded-full overflow-hidden ${backgroundColor} relative ${className}`}>
      {imageLoading && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="h-1/2 w-1/2 animate-pulse bg-sand-300 dark:bg-warm-500 rounded-full"></div>
        </div>
      )}
      <img
        src={actualSrc}
        alt={alt}
        className={`w-full h-full object-cover ${imageLoading ? 'opacity-0' : 'opacity-100'} transition-opacity`}
        onError={handleImageError}
        onLoad={handleImageLoad}
        loading="lazy"
        referrerPolicy="no-referrer"
        crossOrigin="anonymous"
      />
    </div>
  );
}

export default Avatar;