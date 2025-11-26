/**
 * SSE Client for Lambda Function URL Streaming
 * Handles Server-Sent Events from Bedrock Agent via Lambda streaming
 */

import logger from './logger';

export class SSEClient {
  constructor(url, options = {}) {
    this.url = url;
    this.options = options;
    this.controller = null;
  }

  /**
   * Connect and stream responses using fetch ReadableStream
   * @param {Object} body - Request body (ticker, fiscal_year, session_id)
   * @param {Object} callbacks - { onChunk, onComplete, onError, onConnected }
   */
  async stream(body, { onChunk, onComplete, onError, onConnected }) {
    this.controller = new AbortController();

    try {
      logger.log('🌊 Starting SSE stream:', this.url, body);

      const response = await fetch(this.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.options.token && { 'Authorization': `Bearer ${this.options.token}` })
        },
        body: JSON.stringify(body),
        signal: this.controller.signal
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`);
      }

      logger.log('✅ SSE connection established');

      // Read the response stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          logger.log('🏁 SSE stream complete');
          break;
        }

        // Decode and append to buffer
        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE messages (messages end with \n\n)
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // Keep incomplete message in buffer

        for (const message of lines) {
          if (!message.trim()) continue;

          try {
            // Parse SSE format: event: <type>\ndata: <json>
            const eventMatch = message.match(/^event: (.+)\n/);
            const dataMatch = message.match(/data: (.+)/);

            if (!dataMatch) {
              logger.warn('SSE message without data:', message);
              continue;
            }

            const data = JSON.parse(dataMatch[1]);
            const eventType = eventMatch ? eventMatch[1] : 'message';

            logger.log(`📨 SSE event: ${eventType}`, data);

            // Route to appropriate callback
            if (eventType === 'connected' && data.type === 'connected') {
              if (onConnected) onConnected(data);
            } else if (eventType === 'chunk' && data.type === 'chunk') {
              if (onChunk) onChunk(data.text, data);
            } else if (eventType === 'complete' && data.type === 'complete') {
              if (onComplete) onComplete(data);
            } else if (eventType === 'error' && data.type === 'error') {
              throw new Error(data.message || 'Unknown streaming error');
            }
          } catch (parseError) {
            logger.error('Failed to parse SSE message:', parseError, message);
            if (parseError.message && onError) {
              onError(parseError);
              return; // Stop processing on error
            }
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        logger.log('🛑 SSE stream cancelled');
      } else {
        logger.error('❌ SSE streaming error:', error);
        if (onError) onError(error);
      }
    }
  }

  /**
   * Cancel the stream
   */
  cancel() {
    if (this.controller) {
      logger.log('🛑 Cancelling SSE stream');
      this.controller.abort();
      this.controller = null;
    }
  }

  /**
   * Check if stream is active
   */
  isActive() {
    return this.controller !== null;
  }
}

export default SSEClient;
