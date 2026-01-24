/**
 * RatingsHeader Component Tests
 *
 * P1 Tests for the report header showing ticker, verdict badge, and metadata.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import RatingsHeader from '../../../components/research/RatingsHeader';

describe('RatingsHeader', () => {
  describe('Ticker Display', () => {
    it('should display the ticker symbol', () => {
      render(<RatingsHeader ticker="AAPL" />);
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('should display ticker as heading', () => {
      render(<RatingsHeader ticker="NVDA" />);
      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('NVDA');
    });
  });

  describe('Date Display', () => {
    it('should display formatted date when generatedAt is provided', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          generatedAt="2026-01-24T10:00:00Z"
        />
      );
      // Date should be formatted as "Jan 24, 2026"
      expect(screen.getByText('Jan 24, 2026')).toBeInTheDocument();
    });

    it('should not display date when generatedAt is null', () => {
      render(<RatingsHeader ticker="AAPL" generatedAt={null} />);
      expect(screen.queryByText(/\d{4}/)).not.toBeInTheDocument();
    });

    it('should handle invalid date gracefully', () => {
      render(<RatingsHeader ticker="AAPL" generatedAt="invalid-date" />);
      // Should not crash, just not display a date
      expect(screen.getByText('AAPL')).toBeInTheDocument();
    });
  });

  describe('Verdict Badge', () => {
    it('should display BUY verdict with green styling', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'BUY' }}
        />
      );
      expect(screen.getByText('BUY')).toBeInTheDocument();
      // Check for emerald/green styling
      const badge = screen.getByText('BUY').closest('div');
      expect(badge).toHaveClass('bg-emerald-50');
    });

    it('should display SELL verdict with red styling', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'SELL' }}
        />
      );
      expect(screen.getByText('SELL')).toBeInTheDocument();
      const badge = screen.getByText('SELL').closest('div');
      expect(badge).toHaveClass('bg-red-50');
    });

    it('should display HOLD verdict with amber styling', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'HOLD' }}
        />
      );
      expect(screen.getByText('HOLD')).toBeInTheDocument();
      const badge = screen.getByText('HOLD').closest('div');
      expect(badge).toHaveClass('bg-amber-50');
    });

    it('should handle lowercase verdict', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'buy' }}
        />
      );
      expect(screen.getByText('buy')).toBeInTheDocument();
    });

    it('should not display verdict badge when no verdict', () => {
      render(<RatingsHeader ticker="AAPL" ratings={{}} />);
      expect(screen.queryByText(/BUY|SELL|HOLD/)).not.toBeInTheDocument();
    });

    it('should not display verdict badge when ratings is empty', () => {
      render(<RatingsHeader ticker="AAPL" />);
      expect(screen.queryByText(/BUY|SELL|HOLD/)).not.toBeInTheDocument();
    });
  });

  describe('Conviction Display', () => {
    it('should display conviction level when provided', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'BUY', conviction: 'High' }}
        />
      );
      expect(screen.getByText('(High conviction)')).toBeInTheDocument();
    });

    it('should not display conviction when not provided', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'BUY' }}
        />
      );
      expect(screen.queryByText(/conviction/)).not.toBeInTheDocument();
    });
  });

  describe('Complete Header', () => {
    it('should display all elements together', () => {
      render(
        <RatingsHeader
          ticker="MSFT"
          ratings={{ overall_verdict: 'HOLD', conviction: 'Medium' }}
          generatedAt="2026-01-15T08:30:00Z"
        />
      );

      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('Jan 15, 2026')).toBeInTheDocument();
      expect(screen.getByText('HOLD')).toBeInTheDocument();
      expect(screen.getByText('(Medium conviction)')).toBeInTheDocument();
    });
  });
});
