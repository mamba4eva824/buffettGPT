"""
Section Parser for Investment Research Reports

Parses v4.8 report format into individual sections for DynamoDB storage.
Handles dynamic headers with ticker-specific numbers and narratives.
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


# Section definitions with regex patterns for dynamic headers
# Format: (pattern, section_id, display_order, part, icon, fallback_title)
SECTION_DEFINITIONS: List[Tuple[str, str, int, int, str, str]] = [
    # Part 1: Executive Summary
    (r'^##\s*TL;?DR', '01_tldr', 1, 1, 'lightning', 'TL;DR'),
    (r'^##\s*What Does .+? (?:Actually )?Do\??', '02_business', 2, 1, 'building', 'What Do They Do?'),
    (r'^##\s*(?:.+?(?:Report Card|Health Check)|Quick Health Check|Is .+? (?:Actually )?Healthy\?)', '03_health', 3, 1, 'clipboard', 'Quick Health Check'),
    (r'^##\s*Investment Fit(?: Assessment)?', '04_fit', 4, 1, 'target', 'Investment Fit'),
    (r'^##\s*The Verdict', '05_verdict', 5, 1, 'gavel', 'The Verdict'),

    # Part 2: Detailed Analysis - Dynamic headers with numbers/narratives
    # Growth: "From 19% to 12%: The Slowdown Story", "The 47% Rocket Ship", "Flatlined at 3%"
    (r'^##\s*(?:Growth|From \d+%|The \d+%|Flatlined|Revenue)', '06_growth', 6, 2, 'chart-up', 'Growth'),
    # Profitability: "From Red to Black", "77% Margins: The Profit Machine", "Bleeding Cash"
    (r'^##\s*(?:Profitability|From Red|Margins|\d+% Margins|Bleeding|The Profit)', '07_profit', 7, 2, 'piggy-bank', 'Profitability'),
    # Valuation: "30% Off", "Pricey at 2x", "Fair Value?", "No P/E Here"
    (r'^##\s*(?:Valuation|\d+% Off|Pricey|Fair Value|No P/E|What You\'re Paying)', '08_valuation', 8, 2, 'calculator', 'Valuation'),
    # Earnings Quality: "The 200% Gap", "The 24% Employee Tax", "Clean Books"
    (r'^##\s*(?:Earnings Quality|The \d+% Gap|The \d+% Employee|Clean Books|Real Profit)', '09_earnings', 9, 2, 'eye', 'Earnings Quality'),
    # Cash Flow: "The $614M Cash Machine", "Paper Profits", "Empty Pockets"
    (r'^##\s*(?:Cash Flow|The \$[\d.]+[BMK]? Cash|Paper Profits|Empty Pockets|Finally Turning)', '10_cashflow', 10, 2, 'cash', 'Cash Flow'),
    # Debt: "The $2B War Chest", "The $50B Mountain", "From $2.4B to $423M"
    (r'^##\s*(?:Debt|The \$[\d.]+[BMK]? (?:War Chest|Mountain)|More Savings|Climbing Out|From \$[\d.]+[BMK]? to)', '11_debt', 11, 2, 'bank', 'Debt'),
    # Dilution: "Your Slice Stays", "The 24% Employee Tax", "Buying Back Faster", "Death by"
    (r'^##\s*(?:Dilution|Your Slice|The \d+% Employee Tax on Shareholders|Buying Back|Death by)', '12_dilution', 12, 2, 'pie-chart', 'Dilution'),
    # Bull/Bear Cases
    (r'^##\s*Bull Case', '13_bull', 13, 2, 'trending-up', 'Bull Case'),
    (r'^##\s*Bear Case', '14_bear', 14, 2, 'trending-down', 'Bear Case'),
    # Warning Signs
    (r'^##\s*Warning Signs(?: Checklist)?', '15_warnings', 15, 2, 'alert-triangle', 'Warning Signs'),
    # Vibe Check
    (r'^##\s*(?:6-Point )?Vibe Check', '16_vibe', 16, 2, 'check-circle', 'Vibe Check'),

    # Part 3: Real Talk
    (r'^##\s*Real Talk', '17_realtalk', 17, 3, 'message-circle', 'Real Talk'),
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
        content = '\n'.join(content_lines).strip()

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


# Icon mapping for frontend display
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
    '13_bull': 'trending-up',
    '14_bear': 'trending-down',
    '15_warnings': 'alert-triangle',
    '16_vibe': 'check-circle',
    '17_realtalk': 'message-circle',
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
    fiscal_year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Build a single 00_executive item containing ToC + ratings + Part 1 sections.

    This creates the combined executive item for fast initial load (single DynamoDB read).

    Args:
        sections: All parsed sections from the report
        ratings: Ratings dictionary (growth, profitability, debt, etc.)
        ticker: Stock ticker symbol
        generated_at: ISO timestamp when report was generated
        model: Model used to generate the report
        prompt_version: Version of the prompt used
        fiscal_year: Fiscal year of the report

    Returns:
        Dictionary ready for DynamoDB storage with structure:
        {
            'ticker': 'AAPL',
            'section_id': '00_executive',
            'toc': [...],
            'ratings': {...},
            'executive_sections': [
                {'section_id': '01_tldr', 'title': '...', 'content': '...', 'icon': '...', 'word_count': N},
                ...
            ],
            'total_word_count': N,
            'generated_at': '...',
            'model': '...',
            'prompt_version': '...',
            'fiscal_year': N
        }
    """
    # Get Part 1 (executive) sections
    executive_sections = get_executive_sections(sections)

    # Build full ToC for all sections
    toc = build_toc(sections)

    # Build executive sections array with content
    exec_sections_data = [
        {
            'section_id': s.section_id,
            'title': s.title,
            'content': s.content,
            'icon': s.icon,
            'word_count': s.word_count
        }
        for s in executive_sections
    ]

    # Build the combined item
    item = {
        'ticker': ticker.upper(),
        'section_id': '00_executive',
        'toc': toc,
        'ratings': ratings,
        'executive_sections': exec_sections_data,
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
