"""
Section Parser for Investment Research Reports

Parses v4.8, v5.1, and v5.2 report formats into individual sections for DynamoDB storage.
Handles dynamic headers with ticker-specific numbers and narratives.

v5.2 changes vs v5.1:
- Added: Dividend (§13) in Part 2 — dividend yield, payout ratio, sustainability
- Added: Moat (§14) in Part 2 — competitive advantages, switching costs, durability
- Added: Earnings Recap (§17) in Part 2 — latest quarter earnings analysis
- Bull Case renumbered from §13 to §15
- Bear Case renumbered from §14 to §16
- Real Talk renumbered from §15 to §18
- Decision Triggers renumbered from §16 to §19
- Part 2 now has 12 sections (was 9), Part 3 still has 2 sections

v5.1 changes vs v4.8:
- Removed: Warning Signs (§15) and 6-Point Vibe Check (§16) — redundant with Quick Health Check
- Added: Decision Triggers (§16) — actionable watch-list for investors
- Real Talk renumbered from §17 to §15
- Part 2 now has 9 sections (was 11), Part 3 now has 2 sections (was 1)
"""

import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple


@dataclass
class ParsedSection:
    """Represents a parsed section from an investment report."""
    section_id: str
    title: str
    content: str
    display_order: int
    part: int
    icon: str = ""
    word_count: int = 0

    def __post_init__(self):
        """Calculate word count after initialization."""
        if not self.word_count:
            self.word_count = len(self.content.split())


# Section definitions with regex patterns for multiple header formats
# Format: (pattern, section_id, display_order, part, icon, fallback_title)
#
# Supports multiple formats across v4.8 and v5.1:
# - v4.8 numbered: "### 1. TL;DR", "### 6. From 37% to 5%: The Growth Story"
# - v5.1 keyword: "## Growth: From 37% to 5% — The Slowdown Story"
# - Simple: "## TL;DR"
#
# v5.1 removed Warning Signs and Vibe Check (redundant with Quick Health Check)
# and added Decision Triggers in Part 3.
#
SECTION_DEFINITIONS: List[Tuple[str, str, int, int, str, str]] = [
    # Part 1: Executive Summary (same in v4.8 and v5.1)
    # Matches: "### 1. TL;DR", "## TL;DR", "## 1. TL;DR"
    (r'^#{2,3}\s*(?:\d+\.\s*)?TL;?DR', '01_tldr', 1, 1, 'lightning', 'TL;DR'),
    # Matches: "### 2. What Does AAPL Actually Do?", "## What Does AAPL Actually Do?"
    (r'^#{2,3}\s*(?:\d+\.\s*)?What Does .+? (?:Actually )?Do\??', '02_business', 2, 1, 'building', 'What Do They Do?'),
    # Matches: "### 3. Quick Health Check", "## Quick Health Check:"
    (r'^#{2,3}\s*(?:\d+\.\s*)?Quick Health Check', '03_health', 3, 1, 'clipboard', 'Quick Health Check'),
    # Matches: "### 4. Investment Fit Assessment", "## Investment Fit"
    (r'^#{2,3}\s*(?:\d+\.\s*)?Investment Fit', '04_fit', 4, 1, 'target', 'Investment Fit'),
    # Matches: "### 5. The Verdict", "## The Verdict"
    (r'^#{2,3}\s*(?:\d+\.\s*)?The Verdict', '05_verdict', 5, 1, 'gavel', 'The Verdict'),

    # Part 2: Detailed Analysis
    # Matches numbered format "### 6. Title" OR keyword format "## Growth: Title"
    # Growth - matches "### 6. From 37% to 5%", "## Growth:", or any "### 6." header
    (r'^#{2,3}\s*(?:6\.\s+|Growth:)', '06_growth', 6, 2, 'chart-up', 'Growth'),
    # Profitability - matches "### 7. 77% ROE", "## Profitability:"
    (r'^#{2,3}\s*(?:7\.\s+|Profitability:)', '07_profit', 7, 2, 'piggy-bank', 'Profitability'),
    # Valuation - matches "### 8. 53% Off", "## Valuation:"
    (r'^#{2,3}\s*(?:8\.\s+|Valuation:)', '08_valuation', 8, 2, 'calculator', 'Valuation'),
    # Earnings Quality - matches "### 9. The 62.9% Gap", "## Earnings Quality:"
    (r'^#{2,3}\s*(?:9\.\s+|Earnings Quality:)', '09_earnings', 9, 2, 'eye', 'Earnings Quality'),
    # Cash Flow - matches "### 10. The $10.5B Cash Machine", "## Cash Flow:"
    (r'^#{2,3}\s*(?:10\.\s+|Cash Flow:)', '10_cashflow', 10, 2, 'cash', 'Cash Flow'),
    # Debt - matches "### 11. From Net Cash to $10.7B", "## Debt:"
    (r'^#{2,3}\s*(?:11\.\s+|Debt:)', '11_debt', 11, 2, 'bank', 'Debt'),
    # Dilution - matches "### 12. Your Slice Stays", "## Dilution:"
    (r'^#{2,3}\s*(?:12\.\s+|Dilution:)', '12_dilution', 12, 2, 'pie-chart', 'Dilution'),
    # Dividend - matches "## Dividend:", "### 13. Dividend:" (v5.2, keyword-only to avoid collision with old 13. Bull Case)
    (r'^#{2,3}\s*(?:13\.\s+)?Dividend:', '13_dividend', 13, 2, 'coins', 'Dividend'),
    # Moat - matches "## Moat:", "### 14. Moat:" (v5.2, keyword-only to avoid collision with old 14. Bear Case)
    (r'^#{2,3}\s*(?:14\.\s+)?Moat:', '14_moat', 14, 2, 'shield', 'Moat'),
    # Bull Case - matches "### 13. Bull Case", "### 15. Bull Case", "## Bull Case"
    # (v5.2 uses §15, v5.1 uses §13 — both supported)
    (r'^#{2,3}\s*(?:(?:13|15)\.\s+)?Bull Case', '15_bull', 15, 2, 'trending-up', 'Bull Case'),
    # Bear Case - matches "### 14. Bear Case", "### 16. Bear Case", "## Bear Case"
    # (v5.2 uses §16, v5.1 uses §14 — both supported)
    (r'^#{2,3}\s*(?:(?:14|16)\.\s+)?Bear Case', '16_bear', 16, 2, 'trending-down', 'Bear Case'),
    # Earnings Recap - matches "### 15. Earnings Recap:", "### 17. Earnings Recap:", "## Earnings Recap:" (v5.2)
    (r'^#{2,3}\s*(?:(?:15|17)\.\s+)?Earnings Recap:', '17_recap', 17, 2, 'bar-chart-2', 'Earnings Recap'),

    # Part 3: Real Talk
    # Matches "### 15. Real Talk", "### 16. Real Talk", "### 17. Real Talk", "### 18. Real Talk", "## Real Talk"
    # (v5.2 uses §18, v5.1 uses §15, v4.8 uses §17 — all supported)
    (r'^#{2,3}\s*(?:(?:15|16|17|18)\.\s+)?Real Talk', '18_realtalk', 18, 3, 'message-circle', 'Real Talk'),
    # Decision Triggers - matches "### 16. Decision Triggers:", "### 17. Decision Triggers:", "### 19. Decision Triggers:", "## Decision Triggers:" (v5.1+)
    (r'^#{2,3}\s*(?:(?:16|17|19)\.\s+)?Decision Triggers', '19_triggers', 19, 3, 'crosshair', 'Decision Triggers'),
]


def parse_report_sections(report_content: str, ticker: str) -> List[ParsedSection]:
    """
    Parse a complete report into individual sections.

    Args:
        report_content: Full markdown report content
        ticker: Stock ticker (used for fallback title formatting)

    Returns:
        List of ParsedSection objects in order
    """
    sections: List[ParsedSection] = []
    lines = report_content.split('\n')

    # Track section boundaries
    section_starts: List[Tuple[int, str, str, int, int, str, str]] = []

    # Find all section headers
    for i, line in enumerate(lines):
        stripped = line.strip()
        for pattern, section_id, order, part, icon, fallback in SECTION_DEFINITIONS:
            if re.match(pattern, stripped, re.IGNORECASE):
                # Extract actual title from header (remove ## prefix)
                actual_title = re.sub(r'^##\s*', '', stripped)
                section_starts.append((i, section_id, actual_title, order, part, icon, fallback))
                break

    # Extract content between sections
    for idx, (line_num, section_id, title, order, part, icon, fallback) in enumerate(section_starts):
        # Determine end of this section
        if idx + 1 < len(section_starts):
            end_line = section_starts[idx + 1][0]
        else:
            end_line = len(lines)

        # Extract content (skip the header line itself)
        content_lines = lines[line_num + 1:end_line]
        raw_content = '\n'.join(content_lines).strip()

        # Clean content to remove decorative part headers
        content = _clean_section_content(raw_content)

        # Use actual title from report, clean it up
        clean_title = _clean_title(title, fallback)

        sections.append(ParsedSection(
            section_id=section_id,
            title=clean_title,
            content=content,
            display_order=order,
            part=part,
            icon=icon
        ))

    # Sort by display order to ensure consistent ordering
    sections.sort(key=lambda s: s.display_order)

    # Strip trailing JSON ratings block from the last section (typically 19_triggers)
    if sections:
        last = sections[-1]
        stripped_content = _strip_trailing_json_block(last.content)
        if stripped_content != last.content:
            sections[-1] = ParsedSection(
                section_id=last.section_id,
                title=last.title,
                content=stripped_content,
                display_order=last.display_order,
                part=last.part,
                icon=last.icon
            )

    return sections


def _clean_title(title: str, fallback: str) -> str:
    """
    Clean up a section title for display.

    Args:
        title: Raw title from the report
        fallback: Fallback title if cleaning produces empty result

    Returns:
        Cleaned title suitable for display
    """
    # Remove markdown formatting
    cleaned = re.sub(r'\*+', '', title)
    cleaned = re.sub(r'_+', '', cleaned)

    # Remove trailing punctuation that doesn't add meaning
    cleaned = cleaned.rstrip(':')

    # Trim whitespace
    cleaned = cleaned.strip()

    return cleaned if cleaned else fallback


def _strip_trailing_json_block(content: str) -> str:
    """
    Strip a trailing ```json {...} ``` block from section content.

    The ratings JSON block is appended at the end of reports and ends up in
    the last section's content (typically 19_triggers). This removes it so
    users don't see raw JSON in the report.

    Only strips JSON blocks at the END of content to avoid removing
    legitimate JSON examples in the middle of a section.
    """
    # Match a ```json block followed only by optional whitespace at the end
    pattern = r'\n*---\s*\n*```json\s*\{[\s\S]*?\}\s*```\s*$'
    cleaned = re.sub(pattern, '', content)
    if cleaned != content:
        return cleaned.strip()

    # Fallback: ```json block at end without --- separator
    pattern = r'\n*```json\s*\{[\s\S]*?\}\s*```\s*$'
    cleaned = re.sub(pattern, '', content)
    return cleaned.strip()


def _clean_section_content(content: str) -> str:
    """
    Clean up section content by removing decorative part headers.

    Removes patterns like:
    ═══════════════════════════════════════════════════════════════
    ## PART 2: DETAILED ANALYSIS (For Those Who Want to Dig Deeper)
    ═══════════════════════════════════════════════════════════════

    Args:
        content: Raw section content

    Returns:
        Cleaned content without decorative headers
    """
    # Pattern to match decorative part headers (with optional surrounding dividers)
    # Matches: divider line + PART X header + divider line
    part_header_pattern = r'═+\s*\n?\s*##?\s*PART\s+\d+[^\n]*\n?\s*═*'

    # Remove part headers
    cleaned = re.sub(part_header_pattern, '', content, flags=re.IGNORECASE)

    # Also remove standalone part headers without full dividers
    standalone_pattern = r'^##?\s*PART\s+\d+[^\n]*$'
    cleaned = re.sub(standalone_pattern, '', cleaned, flags=re.IGNORECASE | re.MULTILINE)

    # Clean up any resulting multiple blank lines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


def extract_ratings_json(report_content: str) -> Optional[Dict[str, Any]]:
    """
    Extract the JSON ratings block from the end of a report.

    Args:
        report_content: Full markdown report content

    Returns:
        Parsed JSON dict or None if not found/invalid
    """
    # Look for JSON block at the end (marked with ```json)
    json_pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
    matches = re.findall(json_pattern, report_content)

    if not matches:
        return None

    # Use the last JSON block (ratings should be at the end)
    json_str = matches[-1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def build_toc(sections: List[ParsedSection]) -> List[Dict[str, Any]]:
    """
    Build a table of contents from parsed sections.

    Args:
        sections: List of ParsedSection objects

    Returns:
        List of ToC entries as dicts
    """
    return [
        {
            'section_id': s.section_id,
            'title': s.title,
            'display_order': s.display_order,
            'part': s.part,
            'icon': s.icon,
            'word_count': s.word_count
        }
        for s in sections
    ]


def build_merged_toc(sections: List[ParsedSection]) -> List[Dict[str, Any]]:
    """
    Build a table of contents with Part 1 sections merged into single Executive Summary.

    Args:
        sections: List of ParsedSection objects

    Returns:
        List of ToC entries with merged Executive Summary
        (1 Executive Summary + N Part 2/3 sections)
    """
    # Separate Part 1 and Part 2/3 sections
    part1_sections = [s for s in sections if s.part == 1]
    part2_3_sections = [s for s in sections if s.part >= 2]

    # Calculate total word count for merged executive summary
    executive_word_count = sum(s.word_count for s in part1_sections)

    # Build merged ToC: Single Executive Summary entry + individual Part 2/3 entries
    toc = [
        {
            'section_id': '01_executive_summary',
            'title': 'Executive Summary',
            'display_order': 1,
            'part': 1,
            'icon': 'lightning',
            'word_count': executive_word_count
        }
    ]

    # Add Part 2/3 sections with adjusted display_order (starting from 2)
    for i, s in enumerate(sorted(part2_3_sections, key=lambda x: x.display_order)):
        toc.append({
            'section_id': s.section_id,
            'title': s.title,
            'display_order': i + 2,  # Start from 2 since Executive Summary is 1
            'part': s.part,
            'icon': s.icon,
            'word_count': s.word_count
        })

    return toc


def build_merged_executive_summary(sections: List[ParsedSection]) -> Dict[str, Any]:
    """
    Merge Part 1 sections into a single Executive Summary section.

    Args:
        sections: List of all ParsedSection objects

    Returns:
        Dictionary with merged executive summary content
    """
    # Get Part 1 sections sorted by display order
    part1_sections = sorted(
        [s for s in sections if s.part == 1],
        key=lambda x: x.display_order
    )

    # Merge content with section headers
    merged_content = "\n\n".join([
        f"## {s.title}\n\n{s.content}"
        for s in part1_sections
    ])

    total_word_count = sum(s.word_count for s in part1_sections)

    return {
        'section_id': '01_executive_summary',
        'title': 'Executive Summary',
        'content': merged_content,
        'icon': 'lightning',
        'word_count': total_word_count,
        'part': 1,
        'display_order': 1
    }


def get_sections_by_part(sections: List[ParsedSection], part: int) -> List[ParsedSection]:
    """
    Filter sections by part number.

    Args:
        sections: List of all ParsedSection objects
        part: Part number (1=executive, 2=detailed, 3=realtalk)

    Returns:
        Filtered list of sections for the specified part
    """
    return [s for s in sections if s.part == part]


def get_executive_sections(sections: List[ParsedSection]) -> List[ParsedSection]:
    """Get Part 1 (executive summary) sections."""
    return get_sections_by_part(sections, 1)


def get_detailed_sections(sections: List[ParsedSection]) -> List[ParsedSection]:
    """Get Part 2 (detailed analysis) sections."""
    return get_sections_by_part(sections, 2)


def calculate_total_word_count(sections: List[ParsedSection]) -> int:
    """Calculate total word count across all sections."""
    return sum(s.word_count for s in sections)


# Icon mapping for frontend display (v5.2 section IDs)
SECTION_ICONS = {
    '01_tldr': 'lightning',
    '02_business': 'building',
    '03_health': 'clipboard',
    '04_fit': 'target',
    '05_verdict': 'gavel',
    '06_growth': 'chart-up',
    '07_profit': 'piggy-bank',
    '08_valuation': 'calculator',
    '09_earnings': 'eye',
    '10_cashflow': 'cash',
    '11_debt': 'bank',
    '12_dilution': 'pie-chart',
    '13_dividend': 'coins',
    '14_moat': 'shield',
    '15_bull': 'trending-up',
    '16_bear': 'trending-down',
    '17_recap': 'bar-chart-2',
    '18_realtalk': 'message-circle',
    '19_triggers': 'crosshair',
}


# Part labels for display
PART_LABELS = {
    1: 'Executive Summary',
    2: 'Detailed Analysis',
    3: 'Real Talk'
}


def build_executive_item(
    sections: List[ParsedSection],
    ratings: Dict[str, Any],
    ticker: str,
    generated_at: Optional[str] = None,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    fiscal_year: Optional[int] = None,
    company_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a single 00_executive item containing ToC + ratings + merged Executive Summary.

    This creates the combined executive item for fast initial load (single DynamoDB read).
    Part 1 sections (TL;DR, Business, Health Check, Fit, Verdict) are merged into a single
    Executive Summary section for streamlined display.

    Args:
        sections: All parsed sections from the report
        ratings: Ratings dictionary (growth, profitability, debt, etc.)
        ticker: Stock ticker symbol
        generated_at: ISO timestamp when report was generated
        model: Model used to generate the report
        prompt_version: Version of the prompt used
        fiscal_year: Fiscal year of the report
        company_name: Full company name for search (e.g., 'Apple Inc.')

    Returns:
        Dictionary ready for DynamoDB storage with structure:
        {
            'ticker': 'AAPL',
            'section_id': '00_executive',
            'toc': [...],  # 1 Executive Summary + N Part 2/3 sections
            'ratings': {...},
            'executive_summary': {  # Single merged section
                'section_id': '01_executive_summary',
                'title': 'Executive Summary',
                'content': '## TL;DR\\n\\n...\\n\\n## What Do They Do?\\n\\n...',
                'icon': 'lightning',
                'word_count': N,
                'part': 1,
                'display_order': 1
            },
            'total_word_count': N,
            'generated_at': '...',
            'model': '...',
            'prompt_version': '...',
            'fiscal_year': N
        }
    """
    # Build merged ToC (1 executive summary + Part 2/3 sections)
    toc = build_merged_toc(sections)

    # Build merged Executive Summary (single section with all Part 1 content)
    executive_summary = build_merged_executive_summary(sections)

    # Build the combined item
    item = {
        'ticker': ticker.upper(),
        'section_id': '00_executive',
        'toc': toc,
        'ratings': ratings,
        'executive_summary': executive_summary,  # Single merged section
        'total_word_count': calculate_total_word_count(sections)
    }

    # Add optional metadata fields
    if generated_at:
        item['generated_at'] = generated_at
    if model:
        item['model'] = model
    if prompt_version:
        item['prompt_version'] = prompt_version
    if fiscal_year:
        item['fiscal_year'] = fiscal_year
    if company_name:
        item['company_name'] = company_name

    return item


def get_detailed_section_items(
    sections: List[ParsedSection],
    ticker: str,
    generated_at: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Build individual items for Part 2 and Part 3 sections (detailed analysis).

    These are stored as separate DynamoDB items for on-demand loading.

    Args:
        sections: All parsed sections from the report
        ticker: Stock ticker symbol
        generated_at: ISO timestamp when report was generated

    Returns:
        List of dictionaries ready for DynamoDB storage
    """
    detailed_sections = [s for s in sections if s.part >= 2]

    items = []
    for s in detailed_sections:
        item = {
            'ticker': ticker.upper(),
            'section_id': s.section_id,
            'title': s.title,
            'content': s.content,
            'display_order': s.display_order,
            'part': s.part,
            'icon': s.icon,
            'word_count': s.word_count
        }
        if generated_at:
            item['generated_at'] = generated_at
        items.append(item)

    return items
