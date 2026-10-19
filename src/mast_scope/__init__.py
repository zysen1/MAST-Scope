# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""MAST-Scope: failure diagnosis, blame, and targeted repair for multi-agent traces.

The failure labels follow the Multi-Agent System Failure Taxonomy (MAST) from
Cemri et al., "Why Do Multi-Agent LLM Systems Fail?" (arXiv:2503.13657).
"""

from mast_scope.model import Blame, Diagnosis, Finding, RepairResult, Trace
from mast_scope.pipeline import diagnose, repair
from mast_scope.taxonomy import CATEGORIES, MODES, PAPER_URL

__version__ = "0.1.0"
__all__ = [
    "CATEGORIES",
    "MODES",
    "PAPER_URL",
    "Blame",
    "Diagnosis",
    "Finding",
    "RepairResult",
    "Trace",
    "diagnose",
    "repair",
    "__version__",
]
