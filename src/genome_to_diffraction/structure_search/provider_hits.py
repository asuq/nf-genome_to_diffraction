"""Merge PDB sequence and Foldseek hit bundles without changing evidence.

The adapter accepts the two provider-specific structural-hit JSONL files,
validates every typed hit, rejects duplicate immutable hit IDs, sorts by stable
identity/rank fields, and writes one combined JSONL plus checksum-bound
manifest. Empty inputs are valid and remain distinguishable from malformed
input. It performs no ranking across providers, provider request, coordinate
download, or scientific filtering. Input checksums and the adapter version form
the cache boundary.
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from genome_to_diffraction.checksums import (
    atomic_write_json,
    atomic_write_text,
    sha256_file,
)
from genome_to_diffraction.ids import canonical_json_text, content_id
from genome_to_diffraction.schemas.results import StructuralSearchHit
from genome_to_diffraction.status import InputContractError

_ADAPTER_VERSION = "pdb-provider-hit-merge-v1"
_PDB_PROVIDER = "pdb_sequence_mmseqs"
_FOLDSEEK_PROVIDER = "foldseek_prostt5_pdb"


class ProviderHitMergeError(InputContractError):
    """Provider hit bundles cannot be merged without ambiguity."""


@dataclass(frozen=True)
class ProviderHitMergeRequest:
    """The two PDB-provider hit files and an unused output directory."""

    pdb_sequence_hits_jsonl: Path
    foldseek_hits_jsonl: Path
    output_directory: Path


@dataclass(frozen=True)
class ProviderHitMergeOutput:
    """Deterministically ordered combined hits and integrity manifest."""

    hits: tuple[StructuralSearchHit, ...]
    hits_jsonl: Path
    manifest_json: Path


def _load_hits(
    path: Path, *, expected_provider: str
) -> tuple[Path, list[StructuralSearchHit]]:
    resolved = path.resolve(strict=True)
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ProviderHitMergeError(f"cannot read provider hits: {resolved}") from error
    records: list[StructuralSearchHit] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = StructuralSearchHit.model_validate_json(line)
        except (ValidationError, ValueError) as error:
            raise ProviderHitMergeError(
                f"invalid provider hit at {resolved}:{line_number}: {error}"
            ) from error
        if record.provider != expected_provider:
            raise ProviderHitMergeError(
                f"provider hit source differs from its bundle: {resolved}:{line_number}"
            )
        records.append(record)
    return resolved, records


def merge_pdb_provider_hits(
    request: ProviderHitMergeRequest,
) -> ProviderHitMergeOutput:
    """Validate and combine both PDB-provider hit universes."""

    pdb_path, pdb_hits = _load_hits(
        request.pdb_sequence_hits_jsonl, expected_provider=_PDB_PROVIDER
    )
    foldseek_path, foldseek_hits = _load_hits(
        request.foldseek_hits_jsonl, expected_provider=_FOLDSEEK_PROVIDER
    )
    combined = [*pdb_hits, *foldseek_hits]
    identifiers = [item.hit_id for item in combined]
    if len(identifiers) != len(set(identifiers)):
        raise ProviderHitMergeError("provider hit inputs contain duplicate hit IDs")
    hits = tuple(
        sorted(
            combined,
            key=lambda item: (
                item.sequence_group_id,
                item.provider,
                item.provider_rank,
                item.hit_id,
            ),
        )
    )
    output = request.output_directory.absolute()
    if output.exists():
        raise ProviderHitMergeError(f"provider-hit output already exists: {output}")
    output.mkdir(parents=True)
    hits_path = output / "structural_hits.jsonl"
    atomic_write_text(
        hits_path,
        "".join(f"{canonical_json_text(item)}\n" for item in hits),
    )
    input_sha256 = {
        _PDB_PROVIDER: sha256_file(pdb_path, progress=False),
        _FOLDSEEK_PROVIDER: sha256_file(foldseek_path, progress=False),
    }
    identity = {
        "adapter_version": _ADAPTER_VERSION,
        "input_sha256": input_sha256,
        "hit_ids": [item.hit_id for item in hits],
    }
    manifest_path = output / "provider_hit_merge_manifest.json"
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "merge_id": content_id("hitmerge_", identity),
            "adapter_version": _ADAPTER_VERSION,
            "input_sha256": input_sha256,
            "input_hit_counts": {
                _PDB_PROVIDER: len(pdb_hits),
                _FOLDSEEK_PROVIDER: len(foldseek_hits),
            },
            "hit_count": len(hits),
            "hit_ids": [item.hit_id for item in hits],
            "outputs": {
                "structural_hits": {
                    "path": hits_path.name,
                    "sha256": sha256_file(hits_path, progress=False),
                }
            },
        },
    )
    return ProviderHitMergeOutput(
        hits=hits,
        hits_jsonl=hits_path,
        manifest_json=manifest_path,
    )
