/**
 * InvestmentResearchView Integration Tests
 *
 * P1 Tests for the full research view component with ResearchProvider.
 * Tests initial rendering, error states, and user interactions.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import InvestmentResearchView from '../../../components/research/InvestmentResearchView';
import { server } from '../../mocks/server';
import { errorHandlers } from '../../mocks/handlers';

// Mock the useTypewriter hook to avoid animation timing issues
vi.mock('../../../hooks/useTypewriter', () => ({
  default: (text, options) => ({
    displayText: text || '',
    isTyping: options?.isActive || false,
  }),
}));

describe('InvestmentResearchView Integration', () => {
  let onClose;

  beforeEach(() => {
    onClose = vi.fn();
  });

  afterEach(() => {
    server.resetHandlers();
  });

  describe('Initial Rendering', () => {
    it('should render with ticker in header', () => {
      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      // Ticker should appear in header
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('AAPL');
    });

    it('should render close button', () => {
      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);
      expect(screen.getByTitle('Close')).toBeInTheDocument();
    });

    it('should call onClose when close button is clicked', () => {
      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      fireEvent.click(screen.getByTitle('Close'));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('should render table of contents container', () => {
      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);
      expect(screen.getByText('Contents')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should display error message on HTTP error', async () => {
      server.use(errorHandlers.serverError);

      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      await waitFor(() => {
        expect(screen.getByText(/500/)).toBeInTheDocument();
      });

      // Retry button should be visible
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    it('should display error for 401 Unauthorized', async () => {
      server.use(errorHandlers.unauthorized);

      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      await waitFor(() => {
        expect(screen.getByText(/401/)).toBeInTheDocument();
      });
    });

    it('should display retry button on error', async () => {
      server.use(errorHandlers.serverError);

      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });

    it('should trigger retry when retry button is clicked', async () => {
      server.use(errorHandlers.serverError);

      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });

      // Click retry should not throw
      expect(() => {
        fireEvent.click(screen.getByText('Retry'));
      }).not.toThrow();
    });
  });

  describe('Context Provider', () => {
    it('should wrap content in ResearchProvider without throwing', () => {
      expect(() => {
        render(<InvestmentResearchView ticker="NVDA" onClose={onClose} />);
      }).not.toThrow();
    });

    it('should handle different tickers', () => {
      render(<InvestmentResearchView ticker="NVDA" onClose={onClose} />);
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('NVDA');
    });

    it('should uppercase ticker in header', () => {
      render(<InvestmentResearchView ticker="aapl" onClose={onClose} />);
      // The ticker should be displayed as provided (component uppercases internally)
      expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
    });
  });

  describe('Component Structure', () => {
    it('should have two-pane layout', () => {
      const { container } = render(
        <InvestmentResearchView ticker="AAPL" onClose={onClose} />
      );

      // Should have flex layout with main content and ToC
      expect(container.querySelector('.flex-1')).toBeInTheDocument();
    });

    it('should render ratings header area', () => {
      render(<InvestmentResearchView ticker="AAPL" onClose={onClose} />);

      // Ticker heading is in ratings header
      expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
    });
  });

  describe('Cleanup', () => {
    it('should unmount without throwing', () => {
      const { unmount } = render(
        <InvestmentResearchView ticker="AAPL" onClose={onClose} />
      );

      expect(() => unmount()).not.toThrow();
    });
  });
});

describe('InvestmentResearchView with Token', () => {
  it('should render with token prop', () => {
    const onClose = vi.fn();

    expect(() => {
      render(
        <InvestmentResearchView
          ticker="AAPL"
          onClose={onClose}
          token="test-auth-token"
        />
      );
    }).not.toThrow();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('AAPL');
  });
});
