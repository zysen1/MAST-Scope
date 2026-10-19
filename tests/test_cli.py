# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0

import json

from mast_scope.cases import case_by_id
from mast_scope.cli import main


def test_cli_demo_and_roundtrip(tmp_path, capsys):
    assert main(["demo", "--case", "ops-417"]) == 0
    printed = capsys.readouterr().out
    assert "FM-2.4" in printed
    assert "weather" in printed

    path = tmp_path / "trace.json"
    path.write_text(case_by_id("ops-110").trace.model_dump_json(), encoding="utf-8")
    assert main(["diagnose", str(path)]) == 0
    assert "FM-1.1" in capsys.readouterr().out

    out = tmp_path / "cases"
    assert main(["export-demo", str(out)]) == 0
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert len(index["cases"]) == 15
    dossier = json.loads((out / "ops-417.json").read_text(encoding="utf-8"))
    assert dossier["blame"]["mode"] == "FM-2.4"
    assert dossier["repair"]["fully_clean"] is True
