# Copyright 2026 zysen1
# SPDX-License-Identifier: Apache-2.0
"""Command line for diagnosis, repair, demo export, and the offline eval."""

from __future__ import annotations

import argparse
import json
import sys

from mast_scope.cases import case_by_id
from mast_scope.eval.offline import run_offline
from mast_scope.model import Trace
from mast_scope.pipeline import diagnose, repair
from mast_scope.present import export_cases


def _print_diagnosis(diagnosis) -> None:
    if diagnosis.blame is None:
        print(f"{diagnosis.trace_id}: no failure  (judge={diagnosis.judge_backend})")
        return
    blame = diagnosis.blame
    print(
        f"{diagnosis.trace_id}: {blame.mode} {blame.mode_name_en} / {blame.mode_name_zh}\n"
        f"  agent {blame.agent}  step {blame.step_name}  span {blame.span_id}\n"
        f"  category {blame.category} {blame.category_name_en}\n"
        f"  evidence: {blame.evidence}\n"
        f"  chain: {' -> '.join(blame.causal_chain)}\n"
        f"  judge: {diagnosis.judge_backend}  findings: {diagnosis.kept_count}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mast-scope", description="Diagnose a multi-agent trace.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    diagnose_cmd = sub.add_parser("diagnose", help="Diagnose a trace JSON file")
    diagnose_cmd.add_argument("path")

    repair_cmd = sub.add_parser("repair", help="Replan the earliest faulty sub-task")
    repair_cmd.add_argument("path")

    demo = sub.add_parser("demo", help="Print the OPS-417 investigation")
    demo.add_argument("--case", default="ops-417")

    export = sub.add_parser("export-demo", help="Write UI case files")
    export.add_argument("directory")

    sub.add_parser("eval", help="Run the seeded offline evaluation")

    args = parser.parse_args(argv)
    if args.cmd == "diagnose":
        trace = Trace.model_validate_json(open(args.path, encoding="utf-8").read())
        _print_diagnosis(diagnose(trace))
        return 0
    if args.cmd == "repair":
        trace = Trace.model_validate_json(open(args.path, encoding="utf-8").read())
        result = repair(trace)
        if result.plan is None:
            print("nothing to repair")
            return 0
        print(result.plan.instruction_en)
        print(result.plan.instruction_zh)
        print(f"root_cleared={result.root_cleared} fully_clean={result.fully_clean}")
        return 0
    if args.cmd == "demo":
        case = case_by_id(args.case)
        print(case.title_en)
        print(case.title_zh)
        print(case.narrative_en)
        print(case.narrative_zh)
        _print_diagnosis(diagnose(case.trace))
        result = repair(case.trace)
        if result.plan:
            print(result.plan.instruction_en)
            print(f"root_cleared={result.root_cleared} fully_clean={result.fully_clean}")
        return 0
    if args.cmd == "export-demo":
        payloads = export_cases(args.directory)
        print(f"wrote {len(payloads)} cases to {args.directory}")
        return 0
    if args.cmd == "eval":
        metrics = run_offline()
        json.dump(metrics, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
