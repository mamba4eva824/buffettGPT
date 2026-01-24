/**
 * TableOfContents Component Tests
 *
 * P1 Tests for the Table of Contents component used in investment research.
 * Tests highlighting, completion status, and user interactions.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import TableOfContents from '../../../components/research/TableOfContents';
import { MOCK_TOC } from '../../mocks/researchFixtures';

describe('TableOfContents', () => {
  let onSectionClick;

  beforeEach(() => {
    onSectionClick = vi.fn();
  });

  describe('Rendering', () => {
    it('should render empty state when toc is empty', () => {
      render(<TableOfContents toc={[]} />);
      expect(screen.getByText('Loading table of contents...')).toBeInTheDocument();
    });

    it('should render all sections from toc', () => {
      render(<TableOfContents toc={MOCK_TOC} />);

      // Check for section titles (unique names to avoid conflict with part headers)
      expect(screen.getByText('TL;DR Overview')).toBeInTheDocument();
      expect(screen.getByText('Business Overview')).toBeInTheDocument();
      expect(screen.getByText('Competitive Position')).toBeInTheDocument();
    });

    it('should render part headers', () => {
      render(<TableOfContents toc={MOCK_TOC} />);

      // Part headers use partLabels from the component
      expect(screen.getByText('Executive Summary')).toBeInTheDocument(); // Part 1 label
      expect(screen.getByText('Detailed Analysis')).toBeInTheDocument(); // Part 2 label
    });

    it('should display progress badge for each part', () => {
      const streamedSections = {
        '01_executive_summary': { isComplete: true, content: 'Content' },
      };

      render(
        <TableOfContents
          toc={MOCK_TOC}
          streamedSections={streamedSections}
        />
      );

      // Should show 1/5 for Part 1 (5 sections in part 1, 1 complete)
      expect(screen.getByText('1/5')).toBeInTheDocument();
    });
  });

  describe('Active Section Highlighting', () => {
    it('should highlight the active section', () => {
      render(
        <TableOfContents
          toc={MOCK_TOC}
          activeSectionId="01_executive_summary"
          onSectionClick={onSectionClick}
        />
      );

      // Find the button with the active section (TL;DR Overview)
      const activeButton = screen.getByRole('button', { name: /TL;DR Overview/i });
      expect(activeButton).toHaveClass('bg-indigo-50');
    });

    it('should not highlight inactive sections', () => {
      render(
        <TableOfContents
          toc={MOCK_TOC}
          activeSectionId="01_executive_summary"
          onSectionClick={onSectionClick}
        />
      );

      const inactiveButton = screen.getByRole('button', { name: /Business Overview/i });
      expect(inactiveButton).not.toHaveClass('bg-indigo-50');
    });
  });

  describe('Section Status Indicators', () => {
    it('should show spinner for currently streaming section', () => {
      render(
        <TableOfContents
          toc={MOCK_TOC}
          currentStreamingSection="01_executive_summary"
        />
      );

      // The streaming section should have an animated spinner
      const section = screen.getByText('TL;DR Overview').closest('button');
      expect(section.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('should show check mark for completed sections', () => {
      const streamedSections = {
        '01_executive_summary': { isComplete: true, content: 'Full content' },
      };

      render(
        <TableOfContents
          toc={MOCK_TOC}
          streamedSections={streamedSections}
        />
      );

      const section = screen.getByText('TL;DR Overview').closest('button');
      // Check mark icon should be present (emerald-500 color)
      expect(section.querySelector('.text-emerald-500')).toBeInTheDocument();
    });

    it('should show partial indicator for sections with partial content', () => {
      const streamedSections = {
        '01_executive_summary': { isComplete: false, content: 'Partial...' },
      };

      render(
        <TableOfContents
          toc={MOCK_TOC}
          streamedSections={streamedSections}
        />
      );

      const section = screen.getByText('TL;DR Overview').closest('button');
      // Partial indicator is an amber dot
      expect(section.querySelector('.bg-amber-400')).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should call onSectionClick when section is clicked', () => {
      render(
        <TableOfContents
          toc={MOCK_TOC}
          onSectionClick={onSectionClick}
        />
      );

      const sectionButton = screen.getByText('TL;DR Overview').closest('button');
      fireEvent.click(sectionButton);

      expect(onSectionClick).toHaveBeenCalledWith('01_executive_summary');
    });

    it('should toggle part expansion when header is clicked', () => {
      render(<TableOfContents toc={MOCK_TOC} />);

      // Part header "Executive Summary" exists (this is the part 1 label, not a section)
      const partHeader = screen.getByText('Executive Summary').closest('button');
      expect(partHeader).toBeInTheDocument();

      // Click to toggle collapse
      fireEvent.click(partHeader);

      // Part toggle should work without error
      expect(partHeader).toBeInTheDocument();
    });
  });

  describe('Part Grouping', () => {
    it('should group sections by part number', () => {
      const mixedToc = [
        { section_id: 's1', title: 'Part 1 Section', part: 1, icon: 'file-text' },
        { section_id: 's2', title: 'Part 2 Section', part: 2, icon: 'file-text' },
        { section_id: 's3', title: 'Another Part 1', part: 1, icon: 'file-text' },
      ];

      render(<TableOfContents toc={mixedToc} />);

      // Both Part 1 sections should be rendered
      expect(screen.getByText('Part 1 Section')).toBeInTheDocument();
      expect(screen.getByText('Another Part 1')).toBeInTheDocument();
      expect(screen.getByText('Part 2 Section')).toBeInTheDocument();
    });

    it('should auto-expand part containing active section', () => {
      const toc = [
        { section_id: 's1', title: 'Part 2 Section', part: 2, icon: 'file-text' },
      ];

      render(
        <TableOfContents
          toc={toc}
          activeSectionId="s1"
        />
      );

      // The section should be visible (part is expanded)
      expect(screen.getByText('Part 2 Section')).toBeVisible();
    });
  });
});
