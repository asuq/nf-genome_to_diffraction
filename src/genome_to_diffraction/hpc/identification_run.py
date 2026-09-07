"""One-candidate preparation/MR and bounded reporting for identification-screen.

Nextflow alone schedules independent cases. This adapter uses unchanged initial
one-copy MR_AUTO semantics, existing Matthews composition and resource policy.
It never promotes an MR placement to protein identity or refines candidates.
"""

import argparse
import csv
import dataclasses
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import gemmi

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.identification_inputs import (
    MANIFEST_NAME,
    MAX_FILE_BYTES,
    IdentificationCase,
    IdentificationInputError,
    IdentificationPlan,
    execution_cases,
    read_groups,
    safe_member,
    unpack_identification_archive,
    validate_bound_input_root,
)
from genome_to_diffraction.mr.phaser import (
    PhaserParseError,
    parse_completed_phaser_outputs,
    read_phaser_log_evidence,
)
from genome_to_diffraction.mr_resources import (
    build_mr_resource_plan,
    count_polymer_atoms,
    verify_mr_thread_allocation,
)
from genome_to_diffraction.phenix.runtime import stream_from_manifest
from genome_to_diffraction.schemas.io import load_json_document
from genome_to_diffraction.schemas.mr_resources import MrResourcePlan
from genome_to_diffraction.structure_search.pdb_coordinates import (
    PdbCoordinateParseError,
    _pdb_entity,
)


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def load_case(
    root: Path, case_id: str
) -> tuple[IdentificationPlan, IdentificationCase]:
    """Select an exact explicitly executable candidate, never a recent file."""

    plan = IdentificationPlan.model_validate_json((root / "plan.json").read_text())
    found = [c for c in execution_cases(plan) if c.case_id == case_id]
    if len(found) != 1:
        raise IdentificationInputError("candidate is absent from this execution scope")
    return plan, found[0]


def prepare_case(root: Path, case_id: str, outdir: Path) -> None:
    """Extract the authenticated author chain without new model-editing heuristics."""

    plan, case = load_case(root, case_id)
    if case.hit is None or case.coordinate_file is None:
        raise IdentificationInputError("candidate has no ready coordinate")
    coordinate = safe_member(root, case.coordinate_file)
    if sha256_file(coordinate) != case.coordinate_sha256:
        raise IdentificationInputError("candidate coordinate changed")
    groups = read_groups(root / "sequence_groups.jsonl")
    group = groups[case.sequence_group_id]
    crystal = next(c for c in plan.crystals if c.crystal_id == case.crystal_id)
    outdir.mkdir(parents=True, exist_ok=False)
    record = {
        "case_id": case_id,
        "crystal_id": case.crystal_id,
        "sequence_group_id": case.sequence_group_id,
        "started_at": timestamp(),
        "status": "preparing",
        "identity_accepted": False,
    }
    atomic_write_json(outdir / "preparation.json", record)
    try:
        entity = _pdb_entity(coordinate, hit=case.hit)
        structure = gemmi.read_structure(str(coordinate))
        structure.setup_entities()
        if len(structure) != 1:
            raise PdbCoordinateParseError(
                "model coordinate has multiple structural models"
            )
        chains = [c for c in structure[0] if c.name == case.hit.target_chain_or_entity]
        if len(chains) != 1 or not chains[0].get_polymer():
            raise PdbCoordinateParseError(
                "exact model author chain is absent or ambiguous"
            )
        for index in range(len(structure[0]) - 1, -1, -1):
            if structure[0][index].name != case.hit.target_chain_or_entity:
                del structure[0][index]
        chain = structure[0][0]
        for index in range(len(chain) - 1, -1, -1):
            if chain[index].entity_type != gemmi.EntityType.Polymer:
                del chain[index]
        structure.remove_hydrogens()
        chain.name = "A"
        (outdir / "model.pdb").write_text(structure.make_pdb_string())
        (outdir / "candidate.fasta").write_text(
            f">{case.sequence_group_id}\n{group.sequence}\n"
        )
        resources = build_mr_resource_plan(
            owner_kind="mr_hypothesis",
            owner_id=case_id,
            reflection_count=crystal.reflection_count,
            moving_atom_count=count_polymer_atoms(outdir / "model.pdb"),
            searched_copy_count=1,
            fixed_atom_count=0,
            symmetry_multiplicity=crystal.symmetry_multiplicity,
        )
        atomic_write_json(
            outdir / "resource_plan.json", resources.model_dump(mode="json")
        )
        record.update(
            status="prepared",
            template_entity_id=entity.entity_id,
            template_sequence_sha256=entity.sequence_sha256,
            model_sha256=sha256_file(outdir / "model.pdb"),
            sequence_sha256=group.sha256,
            resource_plan=resources.model_dump(mode="json"),
        )
    except PdbCoordinateParseError as error:
        record.update(status="model_preparation_failed", reason=str(error))
    record["completed_at"] = timestamp()
    atomic_write_json(outdir / "preparation.json", record)


def phaser_command(
    plan: IdentificationPlan, case: IdentificationCase, prepared: Path, threads: int
) -> list[str]:
    """Construct unchanged MR_AUTO input with distinct expected/searched copies."""

    if case.hit is None or case.hit.sequence_identity is None or not 1 <= threads <= 16:
        raise IdentificationInputError("invalid Phaser model or thread allocation")
    crystal = next(c for c in plan.crystals if c.crystal_id == case.crystal_id)
    return [
        "phenix.phaser",
        "phaser.mode=MR_AUTO",
        f"phaser.hklin={crystal.mtz}",
        f"phaser.labin={crystal.observation_labels}",
        f"phaser.model={prepared.resolve() / 'model.pdb'}",
        f"phaser.seq_file={prepared.resolve() / 'candidate.fasta'}",
        f"phaser.model_identity={100 * case.hit.sequence_identity:.12g}",
        f"phaser.component_copies={case.component_copies}",
        "phaser.search_copies=1",
        "phaser.keywords.general.root=PHASER",
        f"phaser.keywords.general.jobs={threads}",
        "phaser.keywords.sgalternative.select=none",
        f"phaser.crystal_symmetry.space_group={crystal.space_group}",
    ]


def primary_pdb_metrics(path: Path) -> dict[str, object]:
    """Keep final asset scores and real polymer chains distinct from parser peaks."""

    remarks = [
        line for line in path.read_text().splitlines() if line.startswith("REMARK")
    ]
    llgs = [
        float(match[1])
        for line in remarks
        if (match := re.search(r"Log-Likelihood Gain:\s*([-+\d.eE]+)", line))
    ]
    tfzs = [
        float(value)
        for line in remarks
        if "RFZ=" in line
        for value in re.findall(r"\bTFZ==?\s*([-+\d.eE]+)", line)
    ]
    structure = gemmi.read_structure(str(path))
    structure.setup_entities()
    return {
        "remarks": remarks,
        "llg": llgs[-1] if llgs else None,
        "tfz": tfzs[-1] if tfzs else None,
        "polymer_chains": sum(bool(c.get_polymer()) for m in structure for c in m),
    }


def run_case(
    root: Path,
    case_id: str,
    prepared: Path,
    manifest: Path,
    threads: int,
    attempt: int,
    outdir: Path,
) -> int:
    """Execute one licensed subprocess; preserve failures without inventing no-hits."""

    plan, case = load_case(root, case_id)
    prep = load_json_document(prepared / "preparation.json")
    group = read_groups(root / "sequence_groups.jsonl")[case.sequence_group_id]
    if (
        prepared / "candidate.fasta"
    ).read_text() != f">{case.sequence_group_id}\n{group.sequence}\n":
        raise IdentificationInputError(
            "prepared target sequence differs from the catalogue"
        )
    if (
        not isinstance(prep, dict)
        or prep.get("case_id") != case_id
        or prep.get("status") != "prepared"
        or sha256_file(prepared / "model.pdb") != prep.get("model_sha256")
    ):
        raise IdentificationInputError("prepared model identity differs")
    resource_plan = MrResourcePlan.model_validate_json(
        (prepared / "resource_plan.json").read_text()
    )
    if resource_plan.owner_id != case_id:
        raise IdentificationInputError("resource plan belongs to another candidate")
    resources = verify_mr_thread_allocation(
        plan=resource_plan, resource_attempt=attempt, threads=threads
    )
    crystal = next(c for c in plan.crystals if c.crystal_id == case.crystal_id)
    if sha256_file(Path(crystal.mtz)) != crystal.mtz_sha256:
        raise IdentificationInputError("diffraction changed before MR")
    command = phaser_command(plan, case, prepared, threads)
    outdir.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": "1.0",
        "case_id": case_id,
        "crystal_id": case.crystal_id,
        "sequence_group_id": case.sequence_group_id,
        "accessions": case.accessions,
        "product": case.product,
        "mass_da": case.mass_da,
        "mtz_sha256": crystal.mtz_sha256,
        "model_sha256": prep["model_sha256"],
        "component_copies": case.component_copies,
        "requested_search_copies": 1,
        "attempt": attempt,
        "resources": dataclasses.asdict(resources),
        "resource_plan_id": resource_plan.resource_plan_id,
        "command": command,
        "started_at": timestamp(),
        "status": "running",
        "identity_accepted": False,
    }
    atomic_write_json(outdir / "run.json", record)
    # Slurm/Nextflow owns the reviewed task deadline and resource retries.
    result = stream_from_manifest(
        manifest,
        command,
        working_directory=outdir.resolve(),
        timeout_seconds=None,
        log_path=outdir / "phenix.capture.log",
    )
    record.update(completed_at=timestamp(), exit_code=result.returncode)
    if result.returncode:
        record["status"] = "execution_failed"
    elif not (outdir / "PHASER.log").is_file():
        record["status"] = "output_missing"
    else:
        try:
            parsed = parse_completed_phaser_outputs(
                read_phaser_log_evidence(outdir / "PHASER.log"), outdir
            )
        except PhaserParseError as error:
            record.update(status="failed_parse", reason=str(error))
        else:
            record.update(
                parsed=dataclasses.asdict(parsed),
                status="completed_hit" if parsed.solution_count else "completed_no_hit",
            )
    if (outdir / "PHASER.1.pdb").is_file():
        record["native_primary_pdb_metrics"] = primary_pdb_metrics(
            outdir / "PHASER.1.pdb"
        )
    atomic_write_json(outdir / "run.json", record)
    exit_status = (
        result.returncode if result.returncode >= 0 else 128 - result.returncode
    )
    return (
        exit_status
        if exit_status in {75, 104, *range(130, 146), *range(175, 178)}
        else 0
    )


def summarise(root: Path, results: Path, work_root: Path, outdir: Path) -> None:
    """Inventory all candidates and attempts, retaining bounded diagnostic assets.

    Reflection/map MTZs remain intact on the HPC and are indexed by checksum;
    this routine collects commands, logs, metadata and PDBs, not hundreds of
    duplicate large reflection files. No scientific cache is made reusable.
    """

    plan = IdentificationPlan.model_validate_json((root / "plan.json").read_text())
    outdir.mkdir(parents=True, exist_ok=True)
    trace_path = results / "pipeline_info/trace.tsv"
    trace = (
        list(csv.DictReader(trace_path.open(), delimiter="\t"))
        if trace_path.is_file()
        else []
    )
    attempts: list[dict[str, object]] = []
    artifacts: list[dict[str, object]] = []
    case_ids = {case.case_id for case in plan.cases}
    mr_failed: set[str] = set()
    total = 0
    for row in trace:
        match = re.fullmatch(
            r"identification-(prepare|mr):(identcase_[a-f0-9]{64})", row["tag"]
        )
        if (
            match is None
            or match[2] not in case_ids
            or re.fullmatch(r"[1-9][0-9]{0,9}", row["task_id"]) is None
        ):
            raise IdentificationInputError(
                "trace task identity is outside this input plan"
            )
        case_id = match[2]
        if match[1] == "mr" and row["status"] not in {"COMPLETED", "CACHED"}:
            mr_failed.add(case_id)
        directory = Path(row["workdir"])
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or not directory.resolve().is_relative_to(work_root.resolve())
        ):
            raise IdentificationInputError("trace work directory escaped its run")
        attempts.append(dict(row))
        destination = outdir / "attempts" / row["task_id"]
        destination.mkdir(parents=True, exist_ok=True)
        for name in (
            ".command.sh",
            ".command.run",
            ".command.log",
            ".command.err",
            ".exitcode",
        ):
            path = directory / name
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
                if path.stat().st_size > MAX_FILE_BYTES or total > 10 * 1024**3:
                    raise IdentificationInputError("diagnostic task file exceeds bound")
                shutil.copyfile(path, destination / name)
        # Failed tasks are not published by Nextflow. Preserve their exact
        # candidate-local logs/partial assets rather than losing them at collection.
        if row["status"] not in {"COMPLETED", "CACHED"}:
            child = directory / case_id
            if child.exists():
                if child.is_symlink() or not child.is_dir():
                    raise IdentificationInputError(
                        "unsafe failed-task evidence directory"
                    )
                for path in sorted(child.iterdir()):
                    if path.is_symlink() or not path.is_file():
                        raise IdentificationInputError(
                            "unsafe failed-task evidence file"
                        )
                    copied = path.suffix != ".mtz"
                    size = path.stat().st_size
                    artifacts.append(
                        {
                            "path": "work/" + path.relative_to(work_root).as_posix(),
                            "sha256": sha256_file(path),
                            "size_bytes": size,
                            "collected": copied,
                            "diagnostic_only": True,
                        }
                    )
                    if copied:
                        total += size
                        if size > MAX_FILE_BYTES or total > 10 * 1024**3:
                            raise IdentificationInputError(
                                "failed-task evidence exceeds collection bounds"
                            )
                        shutil.copyfile(path, destination / path.name)
    completed = {}
    for case in plan.cases:
        for role in ("prepared", "mr"):
            directory = results / role / case.case_id
            if not directory.exists():
                continue
            if directory.is_symlink():
                raise IdentificationInputError("result directory is a symlink")
            destination = outdir / role / case.case_id
            destination.mkdir(parents=True, exist_ok=True)
            for path in sorted(directory.iterdir()):
                if path.is_symlink() or not path.is_file():
                    raise IdentificationInputError("unexpected result member")
                size = path.stat().st_size
                digest = sha256_file(path)
                copied = path.suffix != ".mtz"
                artifacts.append(
                    {
                        "path": path.relative_to(results).as_posix(),
                        "sha256": digest,
                        "size_bytes": size,
                        "collected": copied,
                    }
                )
                if copied:
                    total += size
                    if size > MAX_FILE_BYTES or total > 10 * 1024**3:
                        raise IdentificationInputError(
                            "identification collection exceeds fixed bounds"
                        )
                    shutil.copyfile(path, destination / path.name)
            record_path = directory / (
                "run.json" if role == "mr" else "preparation.json"
            )
            if record_path.is_file():
                record = load_json_document(record_path)
                if (
                    not isinstance(record, dict)
                    or record.get("case_id") != case.case_id
                ):
                    raise IdentificationInputError(
                        "published result belongs to another candidate"
                    )
                completed[case.case_id] = record
    selected = {c.case_id for c in execution_cases(plan)}
    rows = [
        {
            "case": c.model_dump(mode="json"),
            "selected_for_this_run": c.case_id in selected,
            "result": completed.get(c.case_id),
            "execution_state": (
                "mr_failed_without_published_result"
                if c.case_id in mr_failed
                and completed.get(c.case_id, {}).get("status") in {None, "prepared"}
                else completed[c.case_id]["status"]
                if c.case_id in completed
                else "unsubmitted_or_missing_evidence"
                if c.case_id in selected
                else "not_selected_for_this_run"
            ),
        }
        for c in plan.cases
    ]
    atomic_write_json(
        outdir / "assessment.json",
        {
            "schema_version": "1.0",
            "run_mode": plan.run_mode,
            "identity_accepted": False,
            "cases": rows,
            "tasks": attempts,
            "artifacts": artifacts,
            "map_mtz_policy": "retained_on_HPC_not_in_bulk_collection",
        },
    )
    shutil.copyfile(root / "plan.json", outdir / "plan.json")
    for name in ("sequence_groups.jsonl", "source_records.jsonl", MANIFEST_NAME):
        shutil.copyfile(root / name, outdir / name)
    for name in ("trace.tsv", "report.html", "timeline.html"):
        if (results / "pipeline_info" / name).is_file():
            shutil.copyfile(results / "pipeline_info" / name, outdir / name)
    lines = [
        f"{sha256_file(path)}  {path.relative_to(outdir).as_posix()}"
        for path in sorted(outdir.rglob("*"))
        if path.is_file() and path.name != "checksums.sha256"
    ]
    (outdir / "checksums.sha256").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--archive", type=Path, required=True)
    unpack.add_argument("--input-id", required=True)
    unpack.add_argument("--source-commit", required=True)
    unpack.add_argument("--allowed-mtz-root", type=Path, required=True)
    unpack.add_argument("--outdir", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--inputs", type=Path, required=True)
    validate.add_argument("--input-id", required=True)
    validate.add_argument("--source-commit", required=True)
    validate.add_argument("--allowed-mtz-root", type=Path, required=True)
    validate.add_argument("--outdir", type=Path, required=True)
    for name in ("prepare", "run"):
        action = sub.add_parser(name)
        action.add_argument("--inputs", type=Path, required=True)
        action.add_argument("--case-id", required=True)
        action.add_argument("--outdir", type=Path, required=True)
        if name == "run":
            action.add_argument("--prepared", type=Path, required=True)
            action.add_argument("--phenix-manifest", type=Path, required=True)
            action.add_argument("--threads", type=int, required=True)
            action.add_argument("--attempt", type=int, required=True)
    summary = sub.add_parser("summarise")
    summary.add_argument("--inputs", type=Path, required=True)
    summary.add_argument("--results", type=Path, required=True)
    summary.add_argument("--work-root", type=Path, required=True)
    summary.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "unpack":
        unpack_identification_archive(
            args.archive,
            args.outdir,
            expected_input_id=args.input_id,
            source_commit=args.source_commit,
            allowed_mtz_root=args.allowed_mtz_root,
        )
    elif args.action == "validate":
        plan = validate_bound_input_root(
            args.inputs,
            expected_input_id=args.input_id,
            source_commit=args.source_commit,
            allowed_mtz_root=args.allowed_mtz_root,
        )
        args.outdir.mkdir(parents=True, exist_ok=False)
        atomic_write_json(
            args.outdir / "execution_cases.json",
            [c.model_dump(mode="json") for c in execution_cases(plan)],
        )
    elif args.action == "prepare":
        prepare_case(args.inputs, args.case_id, args.outdir)
    elif args.action == "run":
        return run_case(
            args.inputs,
            args.case_id,
            args.prepared,
            args.phenix_manifest,
            args.threads,
            args.attempt,
            args.outdir,
        )
    else:
        summarise(args.inputs, args.results, args.work_root, args.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
