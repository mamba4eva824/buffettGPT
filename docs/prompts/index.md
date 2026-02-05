# Prompt Templates

This section documents the prompt versioning strategy and evolution of investment report prompts.

## Overview

BuffettGPT uses versioned prompt templates for investment report generation. Each version is designed to improve report quality, structure, and user experience.

## Current Version

**Recommended: v4.8**

Key features:
- Executive summary first
- Dynamic headers based on content
- Simplified language for accessibility
- Structured section format

## Available Versions

| Version | Status | Key Changes |
|---------|--------|-------------|
| [v4.8](versions/v4_8.md) | **Current** | Executive summary first, dynamic headers |
| [v5.0](versions/v5_0.md) | Experimental | Latest improvements (testing) |

## Version History

### v4.8 (Current)
- Moved executive summary to beginning
- Added dynamic header generation
- Simplified financial terminology
- Improved section transitions

### v5.0 (Experimental)
- Enhanced valuation analysis
- Additional risk factor categories
- Improved comparative analysis
- Testing in progress

## Prompt Structure

Each prompt template includes:

1. **System Instructions**: Role definition and constraints
2. **Data Context**: Financial data placeholders
3. **Section Guidelines**: Format for each report section
4. **Rating Criteria**: How to assign ratings
5. **Output Format**: Markdown structure requirements

## Usage

Prompts are stored in:
```
chat-api/backend/investment_research/prompts/
├── investment_report_prompt_v4_8.txt
├── investment_report_prompt_v5_0.txt
└── (archived versions)
```

### Loading a Prompt

```python
from investment_research.report_generator import ReportGenerator

# Use specific version
generator = ReportGenerator(use_api=False, prompt_version=4.8)

# Available versions
print(ReportGenerator.PROMPT_VERSIONS)
```

## Best Practices

1. **Test new prompts** thoroughly before production use
2. **Keep versions** for rollback capability
3. **Document changes** in version changelog
4. **Use Claude Code mode** for report generation (not API)
