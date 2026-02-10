"""
Unit tests for the section parser module.

Tests both v4.8 format (legacy: includes Warning Signs + Vibe Check)
and v5.1 format (current: replaced with Decision Triggers).
"""

import pytest
from investment_research.section_parser import (
    parse_report_sections,
    extract_ratings_json,
    build_toc,
    build_merged_toc,
    get_executive_sections,
    get_detailed_sections,
    calculate_total_word_count,
    ParsedSection,
    SECTION_DEFINITIONS,
)


# Sample report content for testing (v5.1 format with numbered headers)
# Uses the format that v5.1 prompt produces: "### N. Dynamic Title"
SAMPLE_REPORT = '''
### 1. TL;DR

Apple is the digital bouncer for premium tech. Revenue is flat but they're swimming in cash.
If you want steady returns without drama, this is your stock.

### 2. What Does AAPL Actually Do?

Apple sells premium hardware (iPhones, Macs, iPads) and increasingly sticky services
(App Store, iCloud, Apple Music). Think of them as the toll booth operator for the
premium smartphone lane.

### 3. Quick Health Check

| Category | Question | What's Happening | Flag | What It Means |
|----------|----------|------------------|------|---------------|
| Growth | **How fast are they growing?** | 3% → 4% over 4 quarters | 🟡 | Slow but steady |
| Profit | **Are profits growing?** | Went from 25% to 26% | 🟢 | Getting fatter |

### 4. Investment Fit Assessment

| Investor Type | Verdict | Why |
|---------------|---------|-----|
| Building first portfolio | ✅ | Steady performer |
| Has student debt | ⚠️ | Low yield |

### 5. The Verdict

| Category | Rating | The Short Version |
|----------|--------|-------------------|
| Are they growing? | ⭐⭐⭐ | Slow but steady |
| Are they profitable? | ⭐⭐⭐⭐⭐ | Best in class |

**Overall:** HOLD — Conviction: High

### 6. From 3% to 4%: The Growth Crawl

Apple's growth has slowed dramatically from 19% in 2021 to just 3-4% today.
This isn't surprising for a $3T company, but it means explosive returns are unlikely.

The services business is the bright spot, growing at 12% while hardware flatlines.

**Bottom line:** ~ steady but not exciting

### 7. 77% Margins: The Profit Machine

Apple keeps 77 cents of every dollar after product costs. That's insane.
They've managed to maintain these margins even as hardware sales stall.

**Bottom line:** + pristine margins

### 8. 30% Off: Apple's Cheapest in 5 Years

| The Price Tag | Today | 5-Year Avg | The Discount |
|---------------|-------|------------|--------------|
| Years of Profits (P/E) | 25x | 32x | 22% cheaper |

**Bottom line:** + on sale historically

### 9. Clean Books: What You See Is What You Get

| Step | Real Profit | Minor Adjustments | Almost The Same |
|------|-------------|-------------------|-----------------|
| Reported Net Income | $94B | - | - |
| Stock Compensation | $10B | | 10% gap |

Apple's earnings are clean. Low stock compensation gap.

**Bottom line:** + trustworthy numbers

### 10. The $94B Cash Machine

| Quarter | Cash That Came In | Money Left Over | The Machine |
|---------|-------------------|-----------------|-------------|
| Q1 2026 | $120B | $94B | Strong |

Apple generates mountains of cash. Every dollar of profit turns into cash.

**Bottom line:** + cash machine

### 11. The $50B War Chest

| Year | What They Owe | Cash in Bank | Extra Cash After Debt |
|------|---------------|--------------|----------------------|
| 2026 | $100B | $150B | +$50B ✅ |

Apple has more cash than debt. They could pay off everything tomorrow.

**Bottom line:** + fortress balance sheet

### 12. Buying Back Faster Than They're Printing

| The Scoreboard | The Number | Net Effect |
|----------------|------------|------------|
| Shares Outstanding | -3% YoY | Shrinking |
| Stock Compensation | 2% of revenue | Low |

Apple is shrinking share count by 3% per year. Your slice gets bigger.

**Bottom line:** + buyback king

### 13. Bull Case

1. **Services growth** — 12% growth in high-margin recurring revenue
   - *Evidence:* Services revenue at $24B/quarter, up from $19B two years ago
   - *Impact:* Could add 2-3% to overall margins

2. **Cash machine** — $100B+ annual free cash flow
   - *Evidence:* 5 consecutive years of $90B+ FCF
   - *Impact:* Funds buybacks and dividends without borrowing

**Dream Scenario:** Services hits 30% of revenue, AI features trigger iPhone upgrade super cycle.

### 14. Bear Case

1. **Hardware saturation** — iPhone growth is essentially zero
   - *Likelihood:* High — smartphone market is mature
   - *Damage:* Could cap overall growth at 3-5% indefinitely

2. **China risk** — 20% of revenue, geopolitical tensions
   - *Likelihood:* Medium — ongoing but manageable
   - *Damage:* Could lose $15-20B annual revenue in worst case

**Nightmare Scenario:** China bans iPhone sales, regulation forces App Store fee cuts.

### 15. Real Talk

Apple is the blue chip of blue chips. If you're looking for 100x returns, look elsewhere.
But if you want a steady performer that won't keep you up at night, Apple is your pick.

Remember: this is the toll booth operator for premium smartphones. As long as people
want the best phone, Apple will collect.

### 16. Decision Triggers: Key Numbers to Track for AAPL

| Signal | What to Watch | Current Level | Level to Watch | Why It Matters |
|--------|--------------|---------------|----------------|----------------|
| 🟢 **Bullish signal** | Services revenue crosses 30% of total | 24% | 30% | If services hits 30%, margins expand significantly |
| 🟢 **Bullish signal** | iPhone upgrade cycle accelerates | 3% growth | 8%+ growth | AI features could trigger a super cycle |
| 🔴 **Caution signal** | China revenue drops below 15% | 19% | 15% | Geopolitical risk materializing |
| 🔴 **Caution signal** | Gross margin falls below 43% | 46% | 43% | Could signal pricing pressure |
| ⚡ **Check-in date** | Q2 2026 earnings | April 2026 | — | New data drops — revisit this analysis |

Set a calendar reminder for April 2026.

```json
{
  "growth": {"rating": "Stable", "confidence": "High", "key_factors": ["3% revenue growth", "12% services growth"]},
  "profitability": {"rating": "Very Strong", "confidence": "High", "key_factors": ["77% gross margin", "26% net margin"]},
  "valuation": {"rating": "Strong", "confidence": "High", "pe_vs_5yr_avg_pct": -22, "mean_reversion_signal": "undervalued", "key_factors": ["22% below 5yr avg P/E"]},
  "earnings_quality": {"rating": "Very Strong", "confidence": "High", "gaap_adjusted_gap_pct": 10, "sbc_to_revenue_pct": 2, "key_factors": ["Low SBC", "Clean books"]},
  "cashflow": {"rating": "Very Strong", "confidence": "High", "key_factors": ["$94B FCF", "100% conversion"]},
  "debt": {"rating": "Very Strong", "confidence": "High", "short_term_debt_pct": 10, "key_factors": ["Net cash position", "$50B excess"]},
  "dilution": {"rating": "Very Strong", "confidence": "High", "dilution_pct": -3, "key_factors": ["3% annual buybacks", "Low SBC"]},
  "overall_verdict": "HOLD",
  "conviction": "High"
}
```
'''


class TestParseReportSections:
    """Tests for parse_report_sections function (v5.1 format)."""

    def test_parses_all_sections(self):
        """Should parse all 16 sections from a complete v5.1 report."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        assert len(sections) == 16

    def test_sections_in_order(self):
        """Sections should be sorted by display_order."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        orders = [s.display_order for s in sections]
        assert orders == sorted(orders)

    def test_section_ids_correct(self):
        """Section IDs should match v5.1 expected pattern."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        expected_ids = [
            '01_tldr', '02_business', '03_health', '04_fit', '05_verdict',
            '06_growth', '07_profit', '08_valuation', '09_earnings',
            '10_cashflow', '11_debt', '12_dilution', '13_bull', '14_bear',
            '15_realtalk', '16_triggers'
        ]
        actual_ids = [s.section_id for s in sections]
        assert actual_ids == expected_ids

    def test_part_assignment(self):
        """Sections should be assigned to correct parts (v5.1 layout)."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')

        part1 = [s for s in sections if s.part == 1]
        part2 = [s for s in sections if s.part == 2]
        part3 = [s for s in sections if s.part == 3]

        assert len(part1) == 5  # Executive summary
        assert len(part2) == 9  # Detailed analysis (no Warning Signs or Vibe Check)
        assert len(part3) == 2  # Real Talk + Decision Triggers

    def test_dynamic_header_parsing(self):
        """Should extract dynamic headers correctly."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')

        # Find growth section (has dynamic header "### 6. From 3% to 4%: The Growth Crawl")
        growth = next(s for s in sections if s.section_id == '06_growth')
        assert '3%' in growth.title or 'Growth' in growth.title

        # Find profit section (has "### 7. 77% Margins: The Profit Machine")
        profit = next(s for s in sections if s.section_id == '07_profit')
        assert '77%' in profit.title or 'Margin' in profit.title

    def test_content_extraction(self):
        """Section content should not include the header itself."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')

        tldr = next(s for s in sections if s.section_id == '01_tldr')
        assert not tldr.content.startswith('### 1. TL;DR')
        assert 'digital bouncer' in tldr.content

    def test_word_count_calculated(self):
        """Word count should be calculated for each section."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')

        for section in sections:
            assert section.word_count > 0

    def test_icons_assigned(self):
        """Each section should have an icon."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')

        for section in sections:
            assert section.icon, f"Section {section.section_id} has no icon"


class TestExtractRatingsJson:
    """Tests for extract_ratings_json function."""

    def test_extracts_valid_json(self):
        """Should extract and parse valid JSON from report."""
        ratings = extract_ratings_json(SAMPLE_REPORT)

        assert ratings is not None
        assert 'growth' in ratings
        assert 'overall_verdict' in ratings
        assert ratings['overall_verdict'] == 'HOLD'

    def test_extracts_all_rating_categories(self):
        """Should extract all rating categories."""
        ratings = extract_ratings_json(SAMPLE_REPORT)

        expected_keys = [
            'growth', 'profitability', 'valuation', 'earnings_quality',
            'cashflow', 'debt', 'dilution', 'overall_verdict', 'conviction'
        ]
        for key in expected_keys:
            assert key in ratings

    def test_returns_none_for_missing_json(self):
        """Should return None if no JSON block found."""
        report_without_json = "## TL;DR\n\nSome content here."
        ratings = extract_ratings_json(report_without_json)
        assert ratings is None

    def test_returns_none_for_invalid_json(self):
        """Should return None for malformed JSON."""
        report_with_bad_json = """
## TL;DR

Some content.

```json
{invalid json here}
```
"""
        ratings = extract_ratings_json(report_with_bad_json)
        assert ratings is None


class TestBuildToc:
    """Tests for build_toc function."""

    def test_builds_complete_toc(self):
        """Should build ToC with all v5.1 sections."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        toc = build_toc(sections)

        assert len(toc) == 16

    def test_toc_entry_structure(self):
        """ToC entries should have correct structure."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        toc = build_toc(sections)

        for entry in toc:
            assert 'section_id' in entry
            assert 'title' in entry
            assert 'display_order' in entry
            assert 'part' in entry
            assert 'icon' in entry
            assert 'word_count' in entry


class TestBuildMergedToc:
    """Tests for build_merged_toc function."""

    def test_merges_part1_into_executive_summary(self):
        """Part 1 sections should be merged into single Executive Summary entry."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        merged = build_merged_toc(sections)

        # First entry should be merged executive summary
        assert merged[0]['section_id'] == '01_executive_summary'
        assert merged[0]['title'] == 'Executive Summary'
        assert merged[0]['part'] == 1

    def test_merged_toc_count(self):
        """Merged ToC should have 1 executive + N Part 2/3 sections."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        merged = build_merged_toc(sections)

        # v5.1: 1 executive summary + 9 detailed + 2 real talk = 12
        assert len(merged) == 12

    def test_merged_toc_preserves_part2_3_sections(self):
        """Part 2 and 3 sections should be preserved individually."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        merged = build_merged_toc(sections)

        section_ids = [entry['section_id'] for entry in merged]
        assert '06_growth' in section_ids
        assert '14_bear' in section_ids
        assert '15_realtalk' in section_ids
        assert '16_triggers' in section_ids


class TestGetSectionsByPart:
    """Tests for get_executive_sections and get_detailed_sections."""

    def test_get_executive_sections(self):
        """Should return only Part 1 sections."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        executive = get_executive_sections(sections)

        assert len(executive) == 5
        assert all(s.part == 1 for s in executive)
        assert executive[0].section_id == '01_tldr'
        assert executive[-1].section_id == '05_verdict'

    def test_get_detailed_sections(self):
        """Should return only Part 2 sections."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        detailed = get_detailed_sections(sections)

        assert len(detailed) == 9
        assert all(s.part == 2 for s in detailed)


class TestCalculateTotalWordCount:
    """Tests for calculate_total_word_count function."""

    def test_calculates_total(self):
        """Should sum word counts across all sections."""
        sections = parse_report_sections(SAMPLE_REPORT, 'AAPL')
        total = calculate_total_word_count(sections)

        # Should be sum of all section word counts
        expected = sum(s.word_count for s in sections)
        assert total == expected
        assert total > 0


class TestDynamicHeaderPatterns:
    """Tests for dynamic header pattern matching."""

    def test_growth_numbered_patterns(self):
        """Should match numbered growth header patterns."""
        patterns = [
            "### 6. From 19% to 12%: The Slowdown Story",
            "## 6. The 47% Rocket Ship",
            "### 6. Flatlined at 3%: Is Growth Over?",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            growth_sections = [s for s in sections if s.section_id == '06_growth']
            assert len(growth_sections) == 1, f"Failed to match: {header}"

    def test_growth_keyword_patterns(self):
        """Should match keyword-based growth header patterns."""
        patterns = [
            "## Growth: The Slowdown Story",
            "### Growth: Revenue Growth Numbers",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            growth_sections = [s for s in sections if s.section_id == '06_growth']
            assert len(growth_sections) == 1, f"Failed to match: {header}"

    def test_debt_numbered_patterns(self):
        """Should match numbered debt header patterns."""
        patterns = [
            "### 11. The $2B War Chest",
            "## 11. The $50B Mountain",
            "### 11. From $2.4B to $423M: The Great Paydown",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            debt_sections = [s for s in sections if s.section_id == '11_debt']
            assert len(debt_sections) == 1, f"Failed to match: {header}"

    def test_debt_keyword_patterns(self):
        """Should match keyword-based debt header patterns."""
        patterns = [
            "## Debt: The Great Paydown",
            "### Debt: More Savings Than Debt",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            debt_sections = [s for s in sections if s.section_id == '11_debt']
            assert len(debt_sections) == 1, f"Failed to match: {header}"

    def test_health_check_patterns(self):
        """Should match various health check header patterns."""
        patterns = [
            "## Quick Health Check",
            "### 3. Quick Health Check",
            "## 3. Quick Health Check",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            health_sections = [s for s in sections if s.section_id == '03_health']
            assert len(health_sections) == 1, f"Failed to match: {header}"

    def test_real_talk_patterns(self):
        """Should match Real Talk with both v4.8 (§17) and v5.1 (§15) numbering."""
        patterns = [
            "## Real Talk",
            "## 15. Real Talk",
            "## 17. Real Talk",
            "### 15. Real Talk",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            realtalk = [s for s in sections if s.section_id == '15_realtalk']
            assert len(realtalk) == 1, f"Failed to match: {header}"

    def test_decision_triggers_patterns(self):
        """Should match Decision Triggers header patterns (v5.1)."""
        patterns = [
            "## Decision Triggers: Key Numbers to Track for AAPL",
            "## 16. Decision Triggers: What Could Change the AAPL Story",
            "### 16. Decision Triggers",
            "## Decision Triggers",
        ]
        for header in patterns:
            sections = parse_report_sections(f"{header}\n\nContent here.", 'TEST')
            triggers = [s for s in sections if s.section_id == '16_triggers']
            assert len(triggers) == 1, f"Failed to match: {header}"


class TestParsedSectionDataclass:
    """Tests for ParsedSection dataclass."""

    def test_word_count_auto_calculation(self):
        """Word count should be calculated automatically."""
        section = ParsedSection(
            section_id='01_tldr',
            title='TL;DR',
            content='This is a test with exactly ten words here.',
            display_order=1,
            part=1,
            icon='lightning'
        )
        assert section.word_count == 9

    def test_word_count_override(self):
        """Explicit word count should be preserved."""
        section = ParsedSection(
            section_id='01_tldr',
            title='TL;DR',
            content='This is a test.',
            display_order=1,
            part=1,
            icon='lightning',
            word_count=100
        )
        assert section.word_count == 100
