"""Build the fixed checksum-bound Marmic-to-Viper M4 evidence archive.

The migration deliberately accepts one already collected P2-diverse run rather
than arbitrary caller paths.  It retains every inspectable first-copy solution,
the approved decisions, the exact hypotheses/catalogue/preflight inputs, and the
original run/job provenance.  The Viper dispatcher adds its fixed Phenix
manifest after transfer because that licensed installation is site-local.
"""

import logging
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from tqdm import tqdm

from genome_to_diffraction.checksums import atomic_write_json, sha256_file
from genome_to_diffraction.hpc.models import ValidationError
from genome_to_diffraction.schemas.io import ContractLoadError, load_json_document

_LOGGER = logging.getLogger("genome_to_diffraction.hpc.m4_import")

MARMIC_P2_RUN_ID = "gtd-p2-diverse-20260812T045236Z-5b5100e8651c-1f2fe41a"
MARMIC_P2_COMMIT = "5b5100e8651cae0498ad2d6dd185bf8fb8fbbecb"
MARMIC_P2_JOB_ID = "625935"
MARMIC_REVIEW_SHA256 = (
    "da0604426294602a23f441f6a1aea77ec564e9ef8b091ae588b9b861feef55c4"
)
MARMIC_DECISIONS_SHA256 = (
    "7bbe539cf3c02b253ee94d829af6cf0b516e8eecedc6c784ab12cd707d012e2c"
)
CD6_MTZ_SHA256 = "5eb16c3cc3a21e4b7f22cd611834529801c1829fc0a3156a2b6abc2b3de2f20d"
EXPECTED_SEED_COUNT = 11
MAX_IMPORT_ARCHIVE_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class M4ImportBundle:
    """One immutable local archive and its cross-site identity anchors."""

    archive: Path
    archive_sha256: str
    archive_size_bytes: int
    review_manifest_sha256: str
    decisions_sha256: str
    mtz_sha256: str
    seed_count: int


def _load_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = load_json_document(path)
    except ContractLoadError as error:
        raise ValidationError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _regular(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValidationError(f"required {label} is absent: {path}") from error
    if path.is_symlink() or not resolved.is_file():
        raise ValidationError(f"{label} must be a regular non-symlink file")
    return resolved


def _verify_review_package(review: Path) -> tuple[list[Path], list[str]]:
    if review.is_symlink() or not review.is_dir():
        raise ValidationError("fixed retain-all review package is absent or unsafe")
    manifest_path = _regular(review / "mr_seed_review_manifest.json", "review manifest")
    if sha256_file(manifest_path) != MARMIC_REVIEW_SHA256:
        raise ValidationError("fixed review manifest checksum changed")
    manifest = _load_object(manifest_path, "review manifest")
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ValidationError("review manifest item inventory is absent")
    solution_ids: list[str] = []
    required = [manifest_path]
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValidationError("review manifest contains a non-object item")
        copied = raw_item.get("copied_assets")
        # The immutable Marmic package predates the explicit
        # ``inspectable_solution`` field.  A copied Phaser coordinate and MTZ
        # are its checksum-bound equivalent; log-only no-hit records do not
        # qualify for the 11-seed import.
        inspectable = raw_item.get("inspectable_solution") is True or (
            isinstance(copied, dict)
            and isinstance(copied.get("solution_coordinate"), str)
            and isinstance(copied.get("output_mtz"), str)
        )
        if not inspectable:
            continue
        solution_id = raw_item.get("solution_id")
        checksums = raw_item.get("copied_asset_sha256")
        if (
            not isinstance(solution_id, str)
            or not isinstance(copied, dict)
            or not isinstance(checksums, dict)
        ):
            raise ValidationError("review manifest contains an invalid solution item")
        for key in (
            "command",
            "normalised_result",
            "output_mtz",
            "raw_log",
            "solution_coordinate",
        ):
            relative = copied.get(key)
            expected = checksums.get(key)
            if not isinstance(relative, str) or not isinstance(expected, str):
                raise ValidationError(f"review solution {solution_id} omits {key}")
            relpath = PurePosixPath(relative)
            if relpath.is_absolute() or ".." in relpath.parts:
                raise ValidationError("review manifest contains an unsafe asset path")
            asset = _regular(review.joinpath(*relpath.parts), f"review asset {key}")
            if sha256_file(asset) != expected:
                raise ValidationError(
                    f"review asset checksum changed: {solution_id}/{key}"
                )
            required.append(asset)
        solution_ids.append(solution_id)
    if (
        len(solution_ids) != EXPECTED_SEED_COUNT
        or len(set(solution_ids)) != EXPECTED_SEED_COUNT
    ):
        raise ValidationError(
            f"fixed import requires exactly {EXPECTED_SEED_COUNT} unique solutions"
        )
    for name in (
        "approved_mr_seeds.tsv",
        "mr_seed_approval_candidates.tsv",
        "mr_seed_candidates.html",
        "mr_seed_candidates.tsv",
    ):
        candidate = review / name
        if candidate.exists():
            required.append(_regular(candidate, name))
    return sorted(set(required)), solution_ids


def build_fixed_m4_import_bundle(
    repository: Path,
    destination: Path,
    *,
    progress: bool,
) -> M4ImportBundle:
    """Build the only accepted local P2-to-Viper migration archive."""

    state = repository / ".untracked" / "hpc-test" / MARMIC_P2_RUN_ID
    collected = state / "collected"
    review = state / "review-assets-all/artifacts/qualification/p2-diverse-review"
    review_files, solution_ids = _verify_review_package(review)
    decisions = _regular(
        state / "review-assets-all/m4_experimental_seed_decisions.tsv",
        "approved M4 decisions",
    )
    if sha256_file(decisions) != MARMIC_DECISIONS_SHA256:
        raise ValidationError("fixed M4 decisions checksum changed")
    inputs = {
        "hypotheses.jsonl": _regular(
            collected
            / "artifacts/p2-diverse/first-copy/diverse_first_copy_funnel"
            / "mr_hypotheses.jsonl",
            "P2 hypotheses",
        ),
        "sequence_groups.jsonl": _regular(
            repository
            / ".untracked/m0-qualification/results/catalogue-reference-637975d"
            / "sequence_groups.jsonl",
            "sequence groups",
        ),
        "preflight.jsonl": _regular(
            collected / "artifacts/p0/preflight/mtz_preflight.jsonl",
            "MTZ preflight",
        ),
        "CD6QS2P2G1_5.mtz": _regular(
            repository.parent / "data/X-ray_datasets_for_brute_force_MR/Datasets/"
            "Msheng_CD6QS2P2G1_5_pointeless_scala1.mtz",
            "CD6 MTZ",
        ),
    }
    if sha256_file(inputs["CD6QS2P2G1_5.mtz"]) != CD6_MTZ_SHA256:
        raise ValidationError("fixed CD6 MTZ checksum changed")
    provenance = {
        "run.json": _regular(state / "run.json", "local P2 run record"),
        "job-result.json": _regular(
            collected / "state/job-result.json", "P2 job result"
        ),
        "collection-manifest.json": _regular(
            collected / "manifest.json", "P2 collection manifest"
        ),
        "p2-diverse-summary.json": _regular(
            collected / "artifacts/qualification/p2-diverse-summary.json",
            "P2 summary",
        ),
    }
    run = _load_object(provenance["run.json"], "P2 run record")
    job = _load_object(provenance["job-result.json"], "P2 job result")
    if (
        run.get("run_id") != MARMIC_P2_RUN_ID
        or run.get("commit") != MARMIC_P2_COMMIT
        or job.get("job_id") != MARMIC_P2_JOB_ID
        or job.get("scheduler_state") != "COMPLETED"
        or job.get("exit_code") != 0
        or job.get("failure_class") != "success"
    ):
        raise ValidationError("fixed Marmic P2 provenance no longer matches")

    inventory: dict[str, dict[str, object]] = {}
    members: list[tuple[Path, str]] = []
    for path in review_files:
        relative = path.relative_to(review).as_posix()
        members.append((path, f"review_package/{relative}"))
    members.append((decisions, "decisions.tsv"))
    members.extend((path, f"inputs/{name}") for name, path in inputs.items())
    members.extend((path, f"provenance/{name}") for name, path in provenance.items())
    for source, archive_name in members:
        inventory[archive_name] = {
            "sha256": sha256_file(source),
            "size_bytes": source.stat().st_size,
        }
    manifest = destination.with_name("m4_import_manifest.json")
    atomic_write_json(
        manifest,
        {
            "schema_version": "1.0",
            "adapter_version": "m4-cross-site-import-v1",
            "source_site_id": "marmic",
            "destination_site_id": "viper-cpu",
            "parent_run_id": MARMIC_P2_RUN_ID,
            "parent_job_id": MARMIC_P2_JOB_ID,
            "parent_commit": MARMIC_P2_COMMIT,
            "review_manifest_sha256": MARMIC_REVIEW_SHA256,
            "decisions_sha256": MARMIC_DECISIONS_SHA256,
            "mtz_sha256": CD6_MTZ_SHA256,
            "seed_count": EXPECTED_SEED_COUNT,
            "seed_solution_ids": solution_ids,
            "search_model_derivation": (
                "first_copy_solution_coordinate_rigid_body_derived"
            ),
            "original_model_checksum_preserved_separately": True,
            "site_local_phenix_manifest_added_after_transfer": True,
            "inventory": inventory,
        },
    )
    members.append((manifest, "m4_import_manifest.json"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        tarfile.open(destination, mode="w:gz", format=tarfile.PAX_FORMAT) as archive,
        tqdm(
            total=len(members),
            desc="Building Viper M4 import",
            unit="file",
            disable=not progress,
        ) as progress_bar,
    ):
        for source, archive_name in sorted(members, key=lambda item: item[1]):
            archive.add(source, arcname=archive_name, recursive=False)
            progress_bar.update(1)
    manifest.unlink()
    size = destination.stat().st_size
    if not 1 <= size <= MAX_IMPORT_ARCHIVE_BYTES:
        destination.unlink(missing_ok=True)
        raise ValidationError("M4 import archive exceeds its fixed transfer bound")
    _LOGGER.info(
        "built fixed cross-site M4 import archive",
        extra={"seed_count": EXPECTED_SEED_COUNT, "size_bytes": size},
    )
    return M4ImportBundle(
        archive=destination,
        archive_sha256=sha256_file(destination),
        archive_size_bytes=size,
        review_manifest_sha256=MARMIC_REVIEW_SHA256,
        decisions_sha256=MARMIC_DECISIONS_SHA256,
        mtz_sha256=CD6_MTZ_SHA256,
        seed_count=EXPECTED_SEED_COUNT,
    )
