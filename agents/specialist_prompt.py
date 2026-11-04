"""Output limits shared by the five specialist analysis agents.

Compute, Database, Networking, Security and Reliability all return an
AnalysisResult and all end their prompt with this block. The limits exist
because the answer is capped at DEFAULT_MAX_TOKENS (750): with no hard limit
the model wrote 8-14 long recommendations, reaching 480-750 tokens, and an
answer cut off at the cap is rejected by Groq as tool_use_failed.

The limits match what downstream nodes actually read: compact_analysis
(agents/formatting.py) passes on only the first 4 recommendations, the
first 3 risks and 300 characters of reasoning.
"""

from __future__ import annotations

SPECIALIST_OUTPUT_LIMITS = """Return concrete recommendations, your reasoning, and any risks.

Output limits -- these are STRICT limits, not suggestions. A longer response may be cut off and rejected.
- recommendations: at most 4 items. Each item at most 15 words.
- risks: at most 3 items. Each item at most 15 words.
- reasoning: at most 2 sentences and at most 50 words in total.
Include only the most important, actionable recommendations, most important first.
Do not add items just to reach the maximum -- fewer items is fine.
Return valid structured output matching the AnalysisResult schema exactly
(domain, recommendations, reasoning, risks) and nothing else.
"""
