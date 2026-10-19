# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from mast_scope.eval.offline import run_offline
from mast_scope.present import export_cases

ROOT = Path(__file__).resolve().parents[1]


def test_committed_eval_matches_a_fresh_run():
    committed = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
    fresh = run_offline()
    assert committed["n"] == fresh["n"] == 15
    assert committed["mode_accuracy"] == fresh["mode_accuracy"] == 1.0
    assert committed["blame_span_accuracy"] == fresh["blame_span_accuracy"] == 1.0
    assert committed["category_accuracy"] == fresh["category_accuracy"] == 1.0
    assert committed["repair_root_cleared"] == fresh["repair_root_cleared"] == 1.0
    assert committed["repair_fully_clean"] == fresh["repair_fully_clean"] == 1.0
    assert committed["healthy_false_findings"] == fresh["healthy_false_findings"] == 0
    fresh_rows = {row["id"]: row for row in fresh["rows"]}
    for row in committed["rows"]:
        got = fresh_rows[row["id"]]
        assert got["predicted_mode"] == row["predicted_mode"]
        assert got["predicted_span"] == row["gold_span"]
        assert got["fully_clean"] is True


def test_ui_cases_match_a_fresh_export(tmp_path):
    export_cases(tmp_path)
    bundled = ROOT / "ui" / "public" / "cases"
    for name in ("index.json", "ops-417.json", "ops-000.json"):
        assert json.loads((tmp_path / name).read_text(encoding="utf-8")) == json.loads(
            (bundled / name).read_text(encoding="utf-8")
        )
