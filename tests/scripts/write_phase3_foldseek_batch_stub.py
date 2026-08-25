"""Write complete typed no-hit evidence for a fixed Phase III Foldseek stub."""

import hashlib
import itertools
import sys
from collections.abc import Sequence
from pathlib import Path

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_digest, canonical_json_text, content_id
from genome_to_diffraction.schemas.results import (
    SearchScientificStatus,
    SequenceGroupRecord,
    StructuralSearchResult,
)
from genome_to_diffraction.status import ExecutionStatus


def write_phase3_foldseek_stub_sequence_groups(*, output: Path, count: int) -> Path:
    """Write deterministic, distinct public-only synthetic sequence groups."""

    amino_acids = "ACDEFGHIKLMNPQRSTVWY"
    records: list[SequenceGroupRecord] = []
    for suffix in itertools.islice(itertools.product(amino_acids, repeat=3), count):
        sequence = "M" + "".join(suffix)
        digest = hashlib.sha256(sequence.encode("ascii")).hexdigest()
        records.append(
            SequenceGroupRecord(
                schema_version="1.0",
                sequence_group_id=f"seq_{digest}",
                sha256=digest,
                sequence=sequence,
                length_aa=len(sequence),
                molecular_mass_da=400.0,
                mass_method="synthetic public batch fixture",
                residue_policy="standard_exact",
                source_record_count=1,
            )
        )
    if len(records) != count:
        raise ValueError("synthetic sequence count exceeds the public fixture universe")
    atomic_write_text(
        output, "".join(f"{canonical_json_text(record)}\n" for record in records)
    )
    return output


def write_phase3_foldseek_batch_stub(*, batch: Path, output: Path) -> Path:
    """Retain every input query as a completed synthetic provider no-hit."""

    groups = tuple(
        SequenceGroupRecord.model_validate_json(line)
        for line in (batch / "sequence_groups.jsonl")
        .read_text(encoding="ascii")
        .splitlines()
    )
    output.mkdir(parents=True)
    raw = output / "raw"
    raw.mkdir()
    result_path = raw / "foldseek-results.tsv"
    log_path = raw / "foldseek.log"
    atomic_write_text(result_path, "")
    atomic_write_text(log_path, "synthetic Phase III Foldseek stub; no tool executed\n")
    raw_sha256 = sha256_file(result_path, progress=False)
    log_sha256 = sha256_file(log_path, progress=False)
    results = tuple(
        StructuralSearchResult(
            schema_version="1.0",
            search_id=content_id(
                "srch_", {"sequence_group_id": group.sequence_group_id}
            ),
            sequence_group_id=group.sequence_group_id,
            provider="foldseek_prostt5_pdb",
            database_id="db_phase3_public_stub",
            tool="foldseek",
            tool_version="phase3-public-stub-not-executed",
            adapter_version="prostt5-foldseek-pdb-v5",
            cache_key=canonical_digest({"sequence_sha256": group.sha256}),
            execution_status=ExecutionStatus.COMPLETED_NO_HIT,
            scientific_status=SearchScientificStatus.NO_HIT,
            hit_count=0,
            hits=(),
            raw_result_pointer="raw/foldseek-results.tsv",
            raw_result_sha256=raw_sha256,
            command_log_pointer="raw/foldseek.log",
            command_log_sha256=log_sha256,
        )
        for group in groups
    )
    results_path = output / "search_results.jsonl"
    hits_path = output / "structural_hits.jsonl"
    atomic_write_text(
        results_path,
        "".join(f"{canonical_json_text(result)}\n" for result in results),
    )
    atomic_write_text(hits_path, "")
    atomic_write_json(
        output / "search_manifest.json",
        {
            "schema_version": "1.0",
            "provider": "foldseek_prostt5_pdb",
            "query_count": len(results),
            "deferred_query_count": 0,
            "hit_count": 0,
            "outputs": {
                "search_results": {
                    "path": results_path.name,
                    "sha256": sha256_file(results_path, progress=False),
                },
                "structural_hits": {
                    "path": hits_path.name,
                    "sha256": sha256_file(hits_path, progress=False),
                },
            },
        },
    )
    return output


def main(arguments: Sequence[str] | None = None) -> int:
    """Materialise one batch from exactly two fixed local paths."""

    selected = tuple(sys.argv[1:] if arguments is None else arguments)
    if len(selected) != 2:
        raise SystemExit("expected exactly one batch directory and output directory")
    write_phase3_foldseek_batch_stub(batch=Path(selected[0]), output=Path(selected[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
