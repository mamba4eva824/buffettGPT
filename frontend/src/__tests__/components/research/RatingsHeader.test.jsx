/**
 * RatingsHeader Component Tests
 *
 * P1 Tests for the report header showing ticker, signal pills, and metadata.
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

  describe('Complete Header', () => {
    it('should display ticker and date together', () => {
      render(
        <RatingsHeader
          ticker="MSFT"
          ratings={{ growth: { rating: 'Strong' } }}
          generatedAt="2026-01-15T08:30:00Z"
        />
      );

      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('Jan 15, 2026')).toBeInTheDocument();
      expect(screen.getByText(/Growth: Strong/)).toBeInTheDocument();
    });

    it('should not display verdict or conviction', () => {
      render(
        <RatingsHeader
          ticker="AAPL"
          ratings={{ overall_verdict: 'BUY', conviction: 'High' }}
        />
      );
      expect(screen.queryByText('BUY')).not.toBeInTheDocument();
      expect(screen.queryByText(/conviction/)).not.toBeInTheDocument();
    });
  });
});
