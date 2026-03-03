/**
 * Research Test Fixtures
 *
 * Mock data for testing the investment research system.
 * Section IDs and icons match section_parser.py v5.1 SECTION_DEFINITIONS.
 */

// Mock Table of Contents (v5.1 format — merged executive + Part 2/3 sections)
// In production, the merged TOC has 1 executive_summary entry + individual Part 2/3 sections.
export const MOCK_TOC = [
  { section_id: '01_executive_summary', title: 'Executive Summary', part: 1, icon: 'lightning', word_count: 1900, display_order: 1 },
  { section_id: '06_growth', title: 'Growth: 3% to 4% — The Slow Climb', part: 2, icon: 'chart-up', word_count: 800, display_order: 2 },
  { section_id: '07_profit', title: 'Profitability: 77% Margins — The Profit Machine', part: 2, icon: 'piggy-bank', word_count: 750, display_order: 3 },
  { section_id: '08_valuation', title: 'Valuation: 30% Off — Historic Discount', part: 2, icon: 'calculator', word_count: 700, display_order: 4 },
  { section_id: '09_earnings', title: 'Earnings Quality: Clean Books', part: 2, icon: 'eye', word_count: 650, display_order: 5 },
  { section_id: '10_cashflow', title: 'Cash Flow: The $94B Cash Machine', part: 2, icon: 'cash', word_count: 600, display_order: 6 },
  { section_id: '11_debt', title: 'Debt: The $50B War Chest', part: 2, icon: 'bank', word_count: 550, display_order: 7 },
  { section_id: '12_dilution', title: 'Dilution: Buying Back 3% — Shrinking the Pie', part: 2, icon: 'pie-chart', word_count: 400, display_order: 8 },
  { section_id: '13_bull', title: 'Bull Case', part: 2, icon: 'trending-up', word_count: 350, display_order: 9 },
  { section_id: '14_bear', title: 'Bear Case', part: 2, icon: 'trending-down', word_count: 350, display_order: 10 },
  { section_id: '15_recap', title: 'Earnings Recap: 10 for 12 — The Consistent Beater', part: 2, icon: 'bar-chart-2', word_count: 450, display_order: 11 },
  { section_id: '15_realtalk', title: 'Real Talk', part: 3, icon: 'message-circle', word_count: 500, display_order: 12 },
  { section_id: '16_triggers', title: 'Decision Triggers: Key Numbers to Track', part: 3, icon: 'crosshair', word_count: 400, display_order: 13 },
];

// Mock Ratings
export const MOCK_RATINGS = {
  debt: {
    rating: 'A',
    confidence: 0.85,
    key_factors: ['Low debt-to-equity', 'Strong interest coverage']
  },
  cashflow: {
    rating: 'A+',
    confidence: 0.9,
    key_factors: ['Consistent FCF generation', 'High cash conversion']
  },
  growth: {
    rating: 'B+',
    confidence: 0.75,
    key_factors: ['Moderate revenue growth', 'Expanding margins']
  },
  overall_verdict: 'BUY',
  conviction: 'High'
};

// Mock Section Data
export const MOCK_SECTION_DATA = {
  '01_executive_summary': {
    title: 'Executive Summary',
    content: `## TL;DR\n\nApple Inc. (AAPL) remains a fortress of profitability with a legendary brand moat.`,
    part: 1,
    icon: 'file-text',
    word_count: 600
  },
  '06_growth': {
    title: 'Growth',
    content: `## The Growth Story\n\nApple's growth has normalized post-pandemic.`,
    part: 2,
    icon: 'trending-up',
    word_count: 800
  }
};

// Initial state for reducer tests
export const INITIAL_STATE = {
  selectedTicker: null,
  activeSectionId: null,
  isStreaming: false,
  streamStatus: 'idle',
  reportMeta: null,
  streamedContent: {},
  error: null,
  currentStreamingSection: null,
  followUpMessages: [],
  isFollowUpStreaming: false,
  currentFollowUpMessageId: null
};

// Sample saved report data
export const MOCK_SAVED_REPORT = {
  ticker: 'AAPL',
  reportMeta: {
    toc: MOCK_TOC,
    ratings: MOCK_RATINGS,
    total_word_count: 15000,
    generated_at: '2026-01-20T10:00:00Z'
  },
  streamedContent: {
    '01_executive_summary': {
      title: 'Executive Summary',
      content: MOCK_SECTION_DATA['01_executive_summary'].content,
      isComplete: true,
      part: 1,
      icon: 'lightning',
      word_count: 600
    }
  },
  activeSectionId: '01_executive_summary',
  followUpMessages: []
};
