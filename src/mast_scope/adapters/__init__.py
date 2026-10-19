# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Framework adapters.

OpenAI Agents SDK, LangGraph, and Microsoft Agent Framework are optional
runtime dependencies. Importing this package does not import them.
"""

from mast_scope.adapters.langgraph_adapter import MastScopeLangGraphHandler
from mast_scope.adapters.microsoft import MastScopeSpanProcessor
from mast_scope.adapters.openai_agents import MastScopeProcessor

__all__ = [
    "MastScopeLangGraphHandler",
    "MastScopeProcessor",
    "MastScopeSpanProcessor",
]
