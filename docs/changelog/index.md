# Changelog

This section tracks version history and major changes to BuffettGPT.

## Overview

BuffettGPT follows semantic versioning and maintains detailed changelogs for:

- **Schema Changes**: DynamoDB table modifications
- **API Changes**: Endpoint additions/modifications
- **Feature Releases**: New functionality
- **Bug Fixes**: Issue resolutions

## Recent Changes

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## Major Milestones

### Investment Research Module

| Version | Date | Changes |
|---------|------|---------|
| v2.0 | 2024 | DynamoDB v2 schema with 13 sections per report |
| v1.0 | 2024 | Initial blob-based report storage |

### Follow-up Agent

| Version | Date | Changes |
|---------|------|---------|
| v1.2 | 2024 | 6 integration issues resolved |
| v1.1 | 2024 | Token usage optimization |
| v1.0 | 2024 | Initial Bedrock agent implementation |

### Frontend

| Version | Date | Changes |
|---------|------|---------|
| v2.0 | 2024 | SSE streaming with typewriter effect |
| v1.0 | 2024 | Initial React implementation |

## Schema Evolution

The DynamoDB schema has evolved through several versions:

1. **v1 (Blob)**: Single column for entire report
2. **v2 (Sections)**: 13 individual columns for each section

See [DynamoDB Schema](../infrastructure/dynamodb-schema.md) for migration details.

## Breaking Changes

When making breaking changes:

1. Document in changelog
2. Provide migration scripts
3. Update affected documentation
4. Announce in release notes

## Contributing

When contributing changes:

1. Update the [CHANGELOG.md](CHANGELOG.md) with your changes
2. Follow the existing format
3. Include issue/PR references where applicable
