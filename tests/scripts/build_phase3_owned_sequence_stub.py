"""Build one explicitly synthetic owned sequence package for Nextflow stubs."""

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from genome_to_diffraction.review import (
    PhaseIIIReviewEvidenceSource,
    PhaseIIIReviewPackageRequest,
    build_phase3_review_package,
)
from genome_to_diffraction.schemas.v2 import (
    PhaseIIIExecutionIdentity,
    PhaseIIIReviewCheckpoint,
)


def main() -> None:
    """Materialise an honest stub-only, content-addressed sequence package."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence-checkpoint", type=Path, required=True)
    parser.add_argument("--execution-identity", type=Path, required=True)
    parser.add_argument("--owned-parent-run", required=True)
    parser.add_argument("--crystal-id", required=True)
    parser.add_argument(
        "--checkpoint", choices=("sequence", "composition"), default="sequence"
    )
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    identity = PhaseIIIExecutionIdentity.model_validate_json(
        args.execution_identity.read_bytes()
    )
    catalogue = args.sequence_checkpoint / "provenance/sequence_groups.jsonl"
    group = json.loads(catalogue.read_text(encoding="utf-8").splitlines()[0])
    checkpoint = PhaseIIIReviewCheckpoint(args.checkpoint)
    if checkpoint is PhaseIIIReviewCheckpoint.COMPOSITION:
        finalists = args.sequence_checkpoint / "provenance/finalists.tsv"
        with finalists.open(encoding="ascii", newline="") as stream:
            target_item_ids = tuple(
                row["seed_solution_id"]
                for row in csv.DictReader(stream, delimiter="\t")
            )
    else:
        target_item_ids = (str(group["sequence_group_id"]),)
    args.outdir.mkdir()
    build_phase3_review_package(
        PhaseIIIReviewPackageRequest(
            checkpoint=checkpoint,
            owned_parent_run_id=args.owned_parent_run,
            parent_profile="unknown-single-component",
            parent_phase="phase3-pass1",
            execution_identity_id=identity.execution_identity_id,
            crystal_id=args.crystal_id,
            target_item_ids=target_item_ids,
            created_at=datetime.now(UTC),
            input_root=args.sequence_checkpoint,
            evidence_sources=(
                PhaseIIIReviewEvidenceSource(
                    role="synthetic_sequence_manifest",
                    relative_path="sequence_checkpoint_manifest.json",
                ),
                PhaseIIIReviewEvidenceSource(
                    role="synthetic_catalogue",
                    relative_path="provenance/sequence_groups.jsonl",
                ),
                PhaseIIIReviewEvidenceSource(
                    role="synthetic_source_records",
                    relative_path="provenance/source_records.jsonl",
                ),
            ),
            output_directory=args.outdir,
        )
    )


if __name__ == "__main__":
    main()
