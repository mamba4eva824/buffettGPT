/**
 * StreamingIndicator Component Tests
 *
 * P1 Tests for the streaming status indicator component.
 * Tests status text for each streamStatus value.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import StreamingIndicator from '../../../components/research/StreamingIndicator';

describe('StreamingIndicator', () => {
  describe('Visibility', () => {
    it('should not render when not streaming and status is idle', () => {
      const { container } = render(
        <StreamingIndicator
          isStreaming={false}
          status="idle"
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it('should not render when status is complete', () => {
      const { container } = render(
        <StreamingIndicator
          isStreaming={false}
          status="complete"
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it('should not render when status is error', () => {
      const { container } = render(
        <StreamingIndicator
          isStreaming={false}
          status="error"
        />
      );
      expect(container.firstChild).toBeNull();
    });

    it('should render when status is connecting', () => {
      render(
        <StreamingIndicator
          isStreaming={false}
          status="connecting"
        />
      );
      expect(screen.getByText('Connecting...')).toBeInTheDocument();
    });

    it('should render when isStreaming is true', () => {
      render(
        <StreamingIndicator
          isStreaming={true}
          status="streaming"
        />
      );
      expect(screen.getByText('Loading report...')).toBeInTheDocument();
    });
  });

  describe('Status Text', () => {
    it('should show "Connecting..." when status is connecting', () => {
      render(
        <StreamingIndicator
          isStreaming={false}
          status="connecting"
        />
      );
      expect(screen.getByText('Connecting...')).toBeInTheDocument();
    });

    it('should show "Loading report..." when streaming without current section', () => {
      render(
        <StreamingIndicator
          isStreaming={true}
          status="streaming"
          currentSection={null}
        />
      );
      expect(screen.getByText('Loading report...')).toBeInTheDocument();
    });

    it('should show section name when streaming with current section', () => {
      render(
        <StreamingIndicator
          isStreaming={true}
          status="streaming"
          currentSection="Executive Summary"
        />
      );
      expect(screen.getByText(/Loading Executive Summary/)).toBeInTheDocument();
    });
  });

  describe('Progress Display', () => {
    it('should show progress when provided', () => {
      render(
        <StreamingIndicator
          isStreaming={true}
          status="streaming"
          currentSection="Growth Analysis"
          progress={{ current: 3, total: 13 }}
        />
      );
      expect(screen.getByText('(3/13)')).toBeInTheDocument();
    });

    it('should not show progress when not provided', () => {
      render(
        <StreamingIndicator
          isStreaming={true}
          status="streaming"
          currentSection="Growth Analysis"
        />
      );
      expect(screen.queryByText(/\(\d+\/\d+\)/)).not.toBeInTheDocument();
    });
  });

  describe('Spinner Animation', () => {
    it('should show animated spinner when visible', () => {
      const { container } = render(
        <StreamingIndicator
          isStreaming={true}
          status="streaming"
        />
      );
      // Check for the animate-spin class on the loader icon
      expect(container.querySelector('.animate-spin')).toBeInTheDocument();
    });
  });
});
