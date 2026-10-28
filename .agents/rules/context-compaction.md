---
description: Maintain high context accuracy by targeting a 500K token compaction threshold
trigger: always_on
---

# Context Compaction & Precision Guidelines

- **Context Ceiling**: Keep the active conversation context focused, precise, and under 500,000 tokens (`500K`) to prevent needle-in-a-haystack degradation and context dilution.
- **Compaction Discipline**: When a conversation accumulates extensive logs, diffs, or steps approaching 500K tokens, summarize progress cleanly and execute or recommend `/compact`.
- **High-Signal Transcripts**: Avoid dumping raw multi-megabyte log files or large repeated payloads into context. Query targeted ranges using line offsets or grep filters.
