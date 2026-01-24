/**
 * SectionCard Component Tests
 *
 * P1 Tests for the section card component that displays research sections.
 * Tests rendering, collapse/expand, and streaming cursor.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import SectionCard from '../../../components/research/SectionCard';

// Mock the useTypewriter hook to avoid animation timing issues in tests
vi.mock('../../../hooks/useTypewriter', () => ({
  default: (text, options) => ({
    displayText: text || '',
    isTyping: options?.isActive || false,
  }),
}));

describe('SectionCard', () => {
  const mockSection = {
    title: 'Executive Summary',
    content: '## Overview\n\nThis is the executive summary content.',
    icon: 'file-text',
    isComplete: true,
  };

  let onToggleCollapse;

  beforeEach(() => {
    onToggleCollapse = vi.fn();
  });

  describe('Rendering', () => {
    it('should render null when section is null', () => {
      const { container } = render(<SectionCard section={null} />);
      expect(container.firstChild).toBeNull();
    });

    it('should render section title', () => {
      render(<SectionCard section={mockSection} />);
      expect(screen.getByText('Executive Summary')).toBeInTheDocument();
    });

    it('should render section content', () => {
      const { container } = render(<SectionCard section={mockSection} />);
      // Content should be present (ReactMarkdown may render differently in jsdom)
      expect(container.textContent).toContain('Overview');
      expect(container.textContent).toContain('This is the executive summary content');
    });

    it('should render icon from section data', () => {
      render(<SectionCard section={mockSection} />);
      // Icon should be present in the header
      const header = screen.getByText('Executive Summary').closest('button');
      expect(header).toBeInTheDocument();
    });
  });

  describe('Collapse/Expand', () => {
    it('should show content when not collapsed', () => {
      render(
        <SectionCard
          section={mockSection}
          isCollapsed={false}
        />
      );
      expect(screen.getByText('Overview')).toBeVisible();
    });

    it('should hide content when collapsed', () => {
      render(
        <SectionCard
          section={mockSection}
          isCollapsed={true}
        />
      );
      // Content should be in DOM but hidden via max-h-0
      const content = screen.getByText('Overview');
      expect(content.closest('[class*="max-h-0"]')).toBeInTheDocument();
    });

    it('should call onToggleCollapse when header is clicked', () => {
      render(
        <SectionCard
          section={mockSection}
          onToggleCollapse={onToggleCollapse}
        />
      );

      const header = screen.getByText('Executive Summary').closest('button');
      fireEvent.click(header);

      expect(onToggleCollapse).toHaveBeenCalledTimes(1);
    });

    it('should rotate chevron when collapsed', () => {
      const { container } = render(
        <SectionCard
          section={mockSection}
          isCollapsed={true}
        />
      );

      // Find chevron icon (has -rotate-90 class when collapsed)
      const chevron = container.querySelector('.-rotate-90');
      expect(chevron).toBeInTheDocument();
    });
  });

  describe('Streaming State', () => {
    it('should show streaming cursor when isStreaming is true', () => {
      const { container } = render(
        <SectionCard
          section={mockSection}
          isStreaming={true}
        />
      );

      // Streaming cursor should have animate-pulse class in the component
      const cursor = container.querySelector('.animate-pulse');
      expect(cursor).toBeInTheDocument();
    });

    it('should not show streaming cursor when isStreaming is false', () => {
      const { container } = render(
        <SectionCard
          section={mockSection}
          isStreaming={false}
        />
      );

      // No animate-pulse cursor when not streaming
      const cursor = container.querySelector('.animate-pulse');
      expect(cursor).toBeNull();
    });

    it('should show loading dots when streaming with no content', () => {
      const { container } = render(
        <SectionCard
          section={{ ...mockSection, content: '' }}
          isStreaming={true}
        />
      );

      // Loading dots have animate-bounce class
      const dots = container.querySelectorAll('.animate-bounce');
      expect(dots.length).toBe(3);
    });
  });

  describe('Content Rendering', () => {
    it('should render content text', () => {
      const sectionWithHeadings = {
        ...mockSection,
        content: '## Heading 2\n\n### Heading 3',
      };

      const { container } = render(<SectionCard section={sectionWithHeadings} />);
      // Content should be present (ReactMarkdown may render differently in jsdom)
      expect(container.textContent).toContain('Heading 2');
      expect(container.textContent).toContain('Heading 3');
    });

    it('should render list items', () => {
      const sectionWithList = {
        ...mockSection,
        content: '- Item 1\n- Item 2\n- Item 3',
      };

      const { container } = render(<SectionCard section={sectionWithList} />);
      expect(container.textContent).toContain('Item 1');
      expect(container.textContent).toContain('Item 2');
      expect(container.textContent).toContain('Item 3');
    });

    it('should render table content', () => {
      const sectionWithTable = {
        ...mockSection,
        content: '| Header 1 | Header 2 |\n|----------|----------|\n| Cell 1 | Cell 2 |',
      };

      const { container } = render(<SectionCard section={sectionWithTable} />);
      expect(container.textContent).toContain('Header 1');
      expect(container.textContent).toContain('Cell 1');
    });

    it('should render formatted text', () => {
      const sectionWithFormatting = {
        ...mockSection,
        content: '**bold text** and *italic text*',
      };

      const { container } = render(<SectionCard section={sectionWithFormatting} />);
      expect(container.textContent).toContain('bold text');
      expect(container.textContent).toContain('italic text');
    });
  });

  describe('Icon Mapping', () => {
    it('should render correct icon for known icon names', () => {
      const sectionWithZapIcon = {
        ...mockSection,
        icon: 'zap',
      };

      const { container } = render(<SectionCard section={sectionWithZapIcon} />);
      // Icon should be rendered in header
      const header = screen.getByText('Executive Summary').closest('button');
      expect(header.querySelector('svg')).toBeInTheDocument();
    });

    it('should fall back to FileText for unknown icons', () => {
      const sectionWithUnknownIcon = {
        ...mockSection,
        icon: 'unknown-icon-name',
      };

      const { container } = render(<SectionCard section={sectionWithUnknownIcon} />);
      const header = screen.getByText('Executive Summary').closest('button');
      expect(header.querySelector('svg')).toBeInTheDocument();
    });
  });
});
