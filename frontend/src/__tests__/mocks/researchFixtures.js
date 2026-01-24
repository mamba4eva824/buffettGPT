/**
 * Research Test Fixtures
 *
 * Mock data for testing the investment research system.
 */

// Mock Table of Contents
// Note: Part 1 header is labeled "Executive Summary" in the component, so use different section title
export const MOCK_TOC = [
  { section_id: '01_executive_summary', title: 'TL;DR Overview', part: 1, icon: 'file-text', word_count: 600, display_order: 1 },
  { section_id: '02_business', title: 'Business Overview', part: 1, icon: 'building', word_count: 400, display_order: 2 },
  { section_id: '03_health', title: 'Quick Health Check', part: 1, icon: 'heart-pulse', word_count: 300, display_order: 3 },
  { section_id: '04_fit', title: 'Investment Fit', part: 1, icon: 'target', word_count: 350, display_order: 4 },
  { section_id: '05_verdict', title: 'The Verdict', part: 1, icon: 'gavel', word_count: 250, display_order: 5 },
  { section_id: '06_growth', title: 'Growth Analysis', part: 2, icon: 'trending-up', word_count: 800, display_order: 6 },
  { section_id: '07_profit', title: 'Profitability', part: 2, icon: 'dollar-sign', word_count: 750, display_order: 7 },
  { section_id: '08_valuation', title: 'Valuation', part: 2, icon: 'calculator', word_count: 700, display_order: 8 },
  { section_id: '09_earnings', title: 'Earnings Quality', part: 2, icon: 'bar-chart', word_count: 650, display_order: 9 },
  { section_id: '10_cashflow', title: 'Cash Flow', part: 2, icon: 'banknote', word_count: 600, display_order: 10 },
  { section_id: '11_debt', title: 'Debt Analysis', part: 2, icon: 'credit-card', word_count: 550, display_order: 11 },
  { section_id: '12_dilution', title: 'Dilution Risk', part: 2, icon: 'pie-chart', word_count: 400, display_order: 12 },
  { section_id: '17_realtalk', title: 'Competitive Position', part: 3, icon: 'message-circle', word_count: 500, display_order: 17 }
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
      icon: 'file-text',
      word_count: 600
    }
  },
  activeSectionId: '01_executive_summary',
  followUpMessages: []
};
