"""Explicit RF graph-only simulator, never a scientific receipt generator.

The fixed synthetic scheduling cases exercise positive fan-out, scheduled
no-hit, empty admission and early preparation. These statuses describe the
stub, not the corresponding real benchmark cases. Every emitted document is
marked simulation_only and intentionally does not satisfy a scientific result
schema. The actual reference planner still authenticates the synthetic runner.
"""

import argparse
import json
import sys
from pathlib import Path

CASES = ("M6C001", "M6C010", "M6C055", "M6C025", "M6C037")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(value, dict) or value.get("simulation_only") is not True:
        raise ValueError("RF stub accepts only explicitly simulated stage documents")
    return value


def _write(root: Path, relative: str, value: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({**value, "simulation_only": True}, sort_keys=True) + "\n",
        encoding="ascii",
    )


def _unique_receipts(paths: list[Path], filename: str, fields: tuple[str, ...]) -> set:
    records = [_read(path / "bundle" / filename) for path in paths]
    keys = [tuple(record[field] for field in fields) for record in records]
    if len(keys) != len(set(keys)) or len(paths) != len({p.resolve() for p in paths}):
        raise ValueError("RF stub received duplicate or aliased receipt paths")
    return set(keys)


def main(argv: list[str] | None = None) -> int:
    """Emit one explicitly simulated graph stage without external tools."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "prepare",
            "first",
            "reviews",
            "copy",
            "finalists",
            "refine",
            "identity",
            "aggregate",
        ),
    )
    parser.add_argument("--case-id", choices=CASES)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--hypothesis-id")
    parser.add_argument("--admission-prior")
    parser.add_argument("--seed-id")
    parser.add_argument("--receipt", type=Path, action="append", default=[])
    parser.add_argument("--prepared", type=Path, action="append", default=[])
    parser.add_argument("--identity", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise ValueError("RF stub output must not already exist")
    case_id = args.case_id
    output = args.output
    if args.stage == "prepare":
        if case_id is None:
            raise ValueError("RF preparation stub requires its explicit case")
        status = {
            "M6C001": "materialised",
            "M6C010": "materialised",
            "M6C055": "materialised",
            "M6C025": "completed_no_model",
            "M6C037": "preflight_blocked",
        }[case_id]
        tasks = [
            {"hypothesis": {"hypothesis_id": f"rfstub_{case_id}_{index}"}}
            for index in range(2 if case_id in {"M6C001", "M6C010"} else 0)
        ]
        _write(output, "context.json", {"case_id": case_id, "status": status})
        _write(output, "bundle/reference_prepared_case.json", {"status": status})
        if status == "materialised":
            _write(output, "bundle/cohorts/reference_cohorts.json", {"tasks": tasks})
    elif args.stage == "aggregate":
        prepared = [_read(path) for path in args.prepared]
        identities = [_read(path) for path in args.identity]
        if len(prepared) != len(CASES) or {p["case_id"] for p in prepared} != set(
            CASES
        ):
            raise ValueError("RF stub lost or duplicated a prepared case")
        expected = {p["case_id"] for p in prepared if p["status"] == "materialised"}
        if (
            len(identities) != len(expected)
            or {p["case_id"] for p in identities} != expected
        ):
            raise ValueError("RF stub lost or invented an identity case")
        _write(
            output,
            "bundle/reference_run.json",
            {
                "record_kind": "rf_nextflow_scheduling_stub",
                "native_acceptance_claim": False,
                "benchmark_acceptance_claim": False,
                "human_approval_granted": False,
                "case_ids": sorted(p["case_id"] for p in prepared),
                "identity_case_ids": sorted(expected),
            },
        )
    else:
        if args.upstream is None:
            raise ValueError("RF stub requires its original upstream stage")
        upstream = args.upstream
        context = _read(upstream / "context.json")
        if context["case_id"] != case_id:
            raise ValueError("RF stub context belongs to another case")
        if args.stage == "first":
            tasks = _read(upstream / "bundle/cohorts/reference_cohorts.json")["tasks"]
            if args.hypothesis_id not in {
                row["hypothesis"]["hypothesis_id"] for row in tasks
            }:
                raise ValueError("RF stub received an unscheduled first-copy task")
            _write(
                output,
                "bundle/reference_first_copy.json",
                {
                    "case_id": case_id,
                    "hypothesis_id": args.hypothesis_id,
                },
            )
        elif args.stage == "reviews":
            tasks = _read(upstream / "bundle/cohorts/reference_cohorts.json")["tasks"]
            expected = {(case_id, row["hypothesis"]["hypothesis_id"]) for row in tasks}
            observed = _unique_receipts(
                args.receipt, "reference_first_copy.json", ("case_id", "hypothesis_id")
            )
            if observed != expected:
                raise ValueError("RF stub first-copy receipt union differs")
            selected = [
                {"admission_prior": prior, "seed_solution_id": f"rfstub_{case_id}_seed"}
                for prior in (
                    ("solvent_density", "copy_weighted") if case_id == "M6C001" else ()
                )
            ]
            _write(output, "context.json", {"case_id": case_id})
            _write(output, "copy_tasks.json", {"tasks": selected})
        elif args.stage in {"copy", "refine"}:
            rows = (
                _read(upstream / "copy_tasks.json")["tasks"]
                if args.stage == "copy"
                else [
                    {"admission_prior": row["admission_prior"], **row["task"]}
                    for row in _read(upstream / "bundle/reference_finalists.json")[
                        "tasks"
                    ]
                ]
            )
            if (args.admission_prior, args.seed_id) not in {
                (row["admission_prior"], row["seed_solution_id"]) for row in rows
            }:
                raise ValueError("RF stub received an unscheduled prior/seed task")
            filename = (
                "reference_copy.json"
                if args.stage == "copy"
                else "reference_refinement.json"
            )
            _write(
                output,
                f"bundle/{filename}",
                {
                    "case_id": case_id,
                    "admission_prior": args.admission_prior,
                    "seed_solution_id": args.seed_id,
                },
            )
        elif args.stage == "finalists":
            tasks = _read(upstream / "copy_tasks.json")["tasks"]
            expected = {
                (case_id, row["admission_prior"], row["seed_solution_id"])
                for row in tasks
            }
            observed = _unique_receipts(
                args.receipt,
                "reference_copy.json",
                ("case_id", "admission_prior", "seed_solution_id"),
            )
            if observed != expected:
                raise ValueError("RF stub copy receipt union differs")
            _write(output, "context.json", {"case_id": case_id})
            _write(
                output,
                "bundle/reference_finalists.json",
                {
                    "tasks": [
                        {
                            "admission_prior": row["admission_prior"],
                            "task": {"seed_solution_id": row["seed_solution_id"]},
                        }
                        for row in tasks
                    ],
                },
            )
        elif args.stage == "identity":
            tasks = _read(upstream / "bundle/reference_finalists.json")["tasks"]
            expected = {
                (case_id, row["admission_prior"], row["task"]["seed_solution_id"])
                for row in tasks
            }
            observed = _unique_receipts(
                args.receipt,
                "reference_refinement.json",
                ("case_id", "admission_prior", "seed_solution_id"),
            )
            if observed != expected:
                raise ValueError("RF stub refinement receipt union differs")
            _write(output, "context.json", {"case_id": case_id})
    return 0


if __name__ == "__main__":
    sys.exit(main())
