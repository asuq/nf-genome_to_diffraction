import hashlib
import tempfile
from pathlib import Path

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.ids import canonical_json_text
from tests.scripts.check_nextflow import REPOSITORY, _environment, _read_trace, _run


def _rows(path: Path) -> dict[str, dict[str, str]]:
    rows = {row["tag"]: row for row in _read_trace(path)}
    if len(rows) != 25:
        raise RuntimeError(f"M6 task inventory changed: {sorted(rows)}")
    return rows


def _inventory(row: dict[str, str]) -> dict[str, str]:
    work = Path(row["workdir"])
    files = {
        str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(work.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and not path.relative_to(work).parts[0].startswith(".")
    }
    if not files:
        raise RuntimeError(f"M6 child-output inventory is empty: {row['tag']}")
    return files


def _published(output: Path) -> dict[str, str]:
    return {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file() and "pipeline_info" not in path.parts
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="nf-gtd-m6-cache-", dir="/tmp") as temp:
        root = Path(temp)
        fixtures = REPOSITORY / "tests/fixtures/stubs"
        protocol = root / "protocol.yaml"
        protocol.write_bytes((REPOSITORY / "benchmarks/m6/protocol.yaml").read_bytes())
        params = root / "params.json"
        params.write_text(
            canonical_json_text(
                {
                    "runner_root": str(fixtures / "m6_nextflow/track_plan"),
                    "protocol": str(protocol),
                    "execution_policy": str(
                        REPOSITORY / "benchmarks/m6/execution-nextflow-v1.yaml"
                    ),
                    "software_lock": str(REPOSITORY / "pixi.lock"),
                    "database_manifest": str(fixtures / "database_manifest.json"),
                    "phenix_manifest": str(fixtures / "phenix_install_manifest.json"),
                    "track": "operational",
                }
            ),
            encoding="utf-8",
        )
        output = root / "results"
        command = ["nextflow", "run", "m6_validation.nf", "-profile", "test"]
        command += ["-stub-run", "-params-file", str(params)]
        command += ["--outdir", str(output), "--cache_root", str(root / "cache")]
        environment = _environment(root / "nxf-home")
        _run(command, environment=environment)
        trace = output / "pipeline_info/trace.tsv"
        baseline = _rows(trace)
        if {row["status"] for row in baseline.values()} != {"COMPLETED"}:
            raise RuntimeError("M6 mutation baseline was not 25 completed tasks")
        inventories = {tag: _inventory(row) for tag, row in baseline.items()}
        published = _published(output)

        _run([*command, "-resume"], environment=environment)
        resumed = _rows(trace)
        if {row["status"] for row in resumed.values()} != {"CACHED"}:
            raise RuntimeError("M6 baseline resume was not 25 cached tasks")

        import_tag = f"m6-import:{'a' * 64}"
        child = "m6_catalogue_bundle/catalogue/source_records.jsonl"
        child_path = Path(resumed[import_tag]["workdir"]) / child
        child_bytes = child_path.read_bytes()
        child_path.unlink()
        _run([*command, "-resume"], environment=environment)
        partial = _rows(trace)
        observed = {tag: _inventory(row) for tag, row in partial.items()}
        expected_import = dict(inventories[import_tag])
        expected_import.pop(child)
        if (
            {row["status"] for row in partial.values()} != {"CACHED"}
            or observed[import_tag] != expected_import
            or any(
                observed[tag] != inventories[tag]
                for tag in observed
                if tag != import_tag
            )
        ):
            raise RuntimeError("M6 missing-child HOLD evidence changed")
        child_path.write_bytes(child_bytes)

        protocol.write_bytes(protocol.read_bytes() + b"\n# cache-mutation-probe\n")
        _run([*command, "-resume"], environment=environment)
        mutated = _rows(trace)
        completed = {
            "m6-policy:M6C001",
            "m6-case:M6C001",
            "m6-first:M6C001:hyp_stub",
            "m6-seeds:M6C001",
            "m6-copy:M6C001:sol_stub",
            "m6-finalists:M6C001",
            "m6-refine:M6C001:sol_stub",
            "m6-evidence:M6C001",
            "m6-aggregate:operational",
        }
        actual_completed = {
            tag for tag, row in mutated.items() if row["status"] == "COMPLETED"
        }
        if actual_completed != completed or any(
            row["status"] != "CACHED"
            for tag, row in mutated.items()
            if tag not in completed
        ):
            raise RuntimeError(
                f"M6 protocol mutation closure changed: {actual_completed}"
            )
        for tag, row in mutated.items():
            if tag not in completed and (
                row["hash"] != baseline[tag]["hash"]
                or _inventory(row) != inventories[tag]
            ):
                raise RuntimeError(f"M6 unaffected cache output changed: {tag}")
        if _published(output) != published:
            raise RuntimeError("M6 cache probes changed published scientific outputs")
        atomic_write_json(
            output / "pipeline_info/m6_cache_mutation_evidence.json",
            {
                "baseline_child_outputs": inventories,
                "hold_missing_required_child": child,
                "tasks": {
                    tag: {key: row[key] for key in ("task_id", "hash", "status")}
                    for tag, row in sorted(mutated.items())
                },
                "unaffected_outputs_byte_identical": True,
            },
        )


if __name__ == "__main__":
    main()
