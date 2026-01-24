/**
 * ReportDisplay Component Tests
 *
 * P1 Tests for the main report content display component.
 * Tests markdown rendering, streaming cursor, and placeholder states.
 *
 * Note: ReactMarkdown rendering in jsdom may not fully parse markdown.
 * Tests focus on component behavior rather than full markdown rendering.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import ReportDisplay from '../../../components/research/ReportDisplay';

// Mock the useTypewriter hook
vi.mock('../../../hooks/useTypewriter', () => ({
  default: (text, options) => ({
    displayText: text || '',
    isTyping: options?.isActive || false,
  }),
}));

describe('ReportDisplay', () => {
  describe('Empty State', () => {
    it('should show placeholder when no content and not streaming', () => {
      render(<ReportDisplay content="" isStreaming={false} />);
      expect(screen.getByText(/Select a section from the table of contents/)).toBeInTheDocument();
    });

    it('should not show placeholder when streaming', () => {
      render(<ReportDisplay content="" isStreaming={true} />);
      expect(screen.queryByText(/Select a section/)).not.toBeInTheDocument();
    });

    it('should show loading dots when streaming with no content', () => {
      render(<ReportDisplay content="" isStreaming={true} />);
      const dots = document.querySelectorAll('.animate-bounce');
      expect(dots.length).toBe(3);
    });
  });

  describe('Content Rendering', () => {
    it('should render content text', () => {
      const { container } = render(
        <ReportDisplay
          content="This is some paragraph text about the company."
          isStreaming={false}
        />
      );
      // Content should be present (ReactMarkdown may render as plain text in jsdom)
      expect(container.textContent).toContain('This is some paragraph text');
    });

    it('should render section title when provided', () => {
      render(
        <ReportDisplay
          content="Content here"
          sectionTitle="Growth Analysis"
          isStreaming={false}
        />
      );
      expect(screen.getByText('Growth Analysis')).toBeInTheDocument();
    });

    it('should pass content to ReactMarkdown', () => {
      const { container } = render(
        <ReportDisplay
          content="| Metric | Value |\n| Revenue | $100M |"
          isStreaming={false}
        />
      );
      // Content should appear in the document
      expect(container.textContent).toContain('Revenue');
    });

    it('should render links', () => {
      const { container } = render(
        <ReportDisplay
          content="Check out [Google](https://google.com) for more info."
          isStreaming={false}
        />
      );
      // Link text should be present
      expect(container.textContent).toContain('Google');
    });
  });

  describe('Streaming Cursor', () => {
    it('should show streaming cursor when isStreaming is true', () => {
      const { container } = render(
        <ReportDisplay
          content="Some content"
          isStreaming={true}
        />
      );
      const cursor = container.querySelector('.animate-pulse');
      expect(cursor).toBeInTheDocument();
    });

    it('should not show streaming cursor when isStreaming is false', () => {
      const { container } = render(
        <ReportDisplay
          content="Some content"
          isStreaming={false}
        />
      );
      const cursor = container.querySelector('.animate-pulse');
      expect(cursor).not.toBeInTheDocument();
    });

    it('should show cursor with correct styling', () => {
      const { container } = render(
        <ReportDisplay
          content="Content"
          isStreaming={true}
        />
      );
      const cursor = container.querySelector('.animate-pulse');
      expect(cursor).toHaveClass('bg-indigo-500');
      expect(cursor).toHaveClass('w-2');
      expect(cursor).toHaveClass('h-5');
    });
  });

  describe('Prose Styling', () => {
    it('should apply prose classes for proper typography', () => {
      const { container } = render(
        <ReportDisplay content="Content" isStreaming={false} />
      );
      const article = container.querySelector('article');
      expect(article).toHaveClass('prose');
    });

    it('should support dark mode prose', () => {
      const { container } = render(
        <ReportDisplay content="Content" isStreaming={false} />
      );
      const article = container.querySelector('article');
      expect(article).toHaveClass('dark:prose-invert');
    });

    it('should have max-w-none class', () => {
      const { container } = render(
        <ReportDisplay content="Content" isStreaming={false} />
      );
      const article = container.querySelector('article');
      expect(article).toHaveClass('max-w-none');
    });
  });

  describe('Container Structure', () => {
    it('should have article element for content', () => {
      const { container } = render(
        <ReportDisplay content="Content" isStreaming={false} />
      );
      expect(container.querySelector('article')).toBeInTheDocument();
    });

    it('should have scrollable container', () => {
      const { container } = render(
        <ReportDisplay content="Long content" isStreaming={false} />
      );
      const scrollContainer = container.firstChild;
      expect(scrollContainer).toHaveClass('overflow-y-auto');
    });

    it('should have scrollbar styling classes', () => {
      const { container } = render(
        <ReportDisplay content="Content" isStreaming={false} />
      );
      const scrollContainer = container.firstChild;
      expect(scrollContainer).toHaveClass('scrollbar-thin');
    });

    it('should have height and padding classes', () => {
      const { container } = render(
        <ReportDisplay content="Content" isStreaming={false} />
      );
      const scrollContainer = container.firstChild;
      expect(scrollContainer).toHaveClass('h-full');
      expect(scrollContainer).toHaveClass('px-6');
      expect(scrollContainer).toHaveClass('py-4');
    });
  });
});
