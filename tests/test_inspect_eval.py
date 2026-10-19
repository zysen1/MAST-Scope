# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0

import pytest


def test_inspect_eval_matches_offline(tmp_path, monkeypatch):
    pytest.importorskip("inspect_ai")
    monkeypatch.setenv("INSPECT_LOG_DIR", str(tmp_path))
    from inspect_ai import eval as inspect_eval

    from mast_scope.eval.inspect_task import mast_failure_diagnosis

    logs = inspect_eval(
        mast_failure_diagnosis(),
        model="mockllm/model",
        display="none",
        log_dir=str(tmp_path),
    )
    assert len(logs) == 1
    scores = {score.name: score.metrics["accuracy"].value for score in logs[0].results.scores}
    assert scores["mode_accuracy"] == 1.0
    assert scores["blame_span_accuracy"] == 1.0
