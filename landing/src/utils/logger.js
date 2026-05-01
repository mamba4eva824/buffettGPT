/**
 * Environment-Aware Logger Utility
 *
 * Provides centralized logging that respects environment configuration.
 * In production, all logs are suppressed except critical errors to prevent:
 * - Data leakage through browser console
 * - Exposure of sensitive information (tokens, user data, API responses)
 * - Security vulnerabilities from verbose logging
 *
 * Usage:
 *   import logger from './utils/logger';
 *   logger.log('Debug message');
 *   logger.warn('Warning message');
 *   logger.error('Error message');
 */

const ENV_CONFIG = {
  ENABLE_DEBUG_LOGS: import.meta.env.VITE_ENABLE_DEBUG_LOGS === 'true',
  ENVIRONMENT: import.meta.env.VITE_ENVIRONMENT || 'development'
};

/**
 * Sanitizes sensitive data from objects before logging
 * Removes or masks tokens, passwords, and other sensitive fields
 */
function sanitizeData(data) {
  if (!data || typeof data !== 'object') {
    return data;
  }

  const sensitiveKeys = [
    'token',
    'authorization',
    'password',
    'secret',
    'api_key',
    'apikey',
    'access_token',
    'refresh_token',
    'jwt',
    'bearer'
  ];

  const sanitized = Array.isArray(data) ? [...data] : { ...data };

  for (const key in sanitized) {
    const lowerKey = key.toLowerCase();

    // Mask sensitive keys
    if (sensitiveKeys.some(sensitive => lowerKey.includes(sensitive))) {
      sanitized[key] = '[REDACTED]';
    }
    // Recursively sanitize nested objects
    else if (typeof sanitized[key] === 'object' && sanitized[key] !== null) {
      sanitized[key] = sanitizeData(sanitized[key]);
    }
  }

  return sanitized;
}

/**
 * Logger class with environment-aware methods
 */
class Logger {
  constructor() {
    this.enabled = ENV_CONFIG.ENABLE_DEBUG_LOGS;
    this.environment = ENV_CONFIG.ENVIRONMENT;
  }

  /**
   * General debug logging - disabled in production
   */
  log(...args) {
    if (this.enabled) {
      const sanitized = args.map(arg =>
        typeof arg === 'object' ? sanitizeData(arg) : arg
      );
      console.log(...sanitized);
    }
  }

  /**
   * Debug-level logging - disabled in production
   */
  debug(...args) {
    if (this.enabled) {
      const sanitized = args.map(arg =>
        typeof arg === 'object' ? sanitizeData(arg) : arg
      );
      console.debug(...sanitized);
    }
  }

  /**
   * Info-level logging - disabled in production
   */
  info(...args) {
    if (this.enabled) {
      const sanitized = args.map(arg =>
        typeof arg === 'object' ? sanitizeData(arg) : arg
      );
      console.info(...sanitized);
    }
  }

  /**
   * Warning-level logging - disabled in production
   */
  warn(...args) {
    if (this.enabled) {
      const sanitized = args.map(arg =>
        typeof arg === 'object' ? sanitizeData(arg) : arg
      );
      console.warn(...sanitized);
    }
  }

  /**
   * Error-level logging - ALWAYS enabled (even in production)
   * Sanitizes sensitive data before logging
   */
  error(...args) {
    // Always log errors, but sanitize sensitive data
    const sanitized = args.map(arg =>
      typeof arg === 'object' ? sanitizeData(arg) : arg
    );
    console.error(...sanitized);
  }

  /**
   * Check if debug logging is enabled
   */
  isDebugEnabled() {
    return this.enabled;
  }

  /**
   * Get current environment
   */
  getEnvironment() {
    return this.environment;
  }
}

// Export singleton instance
const logger = new Logger();

export default logger;