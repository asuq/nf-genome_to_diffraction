"""Command-line entry point for contracts and foundation utilities."""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from genome_to_diffraction import __version__
from genome_to_diffraction.catalogue import CatalogueImportRequest, import_catalogues
from genome_to_diffraction.checksums import atomic_write_text
from genome_to_diffraction.databases.prepare import (
    DEFAULT_MINIMUM_FREE_BYTES,
    DEFAULT_STORAGE_LIMIT_BYTES,
    ESM_ATLAS_PROBE_URL,
    PDB_SEQUENCE_URL,
    DatabasePreparationRequest,
    prepare,
)
from genome_to_diffraction.diffraction import (
    FreeRGenerationRequest,
    PreflightRequest,
    generate_free_r,
    preflight_crystals,
)
from genome_to_diffraction.ids import canonical_json_text
from genome_to_diffraction.logging import configure_logging, parse_log_level
from genome_to_diffraction.matthews import MatthewsRequest, enumerate_matthews
from genome_to_diffraction.phenix.errors import PhenixInstallCommandError
from genome_to_diffraction.phenix.installer import InstallRequest, install_phenix
from genome_to_diffraction.phenix.recovery import (
    RecoveryRequest,
    recover_failed_install,
)
from genome_to_diffraction.phenix.runtime import (
    execute_from_manifest,
    verify_manifest,
)
from genome_to_diffraction.schema_check import validate_repository
from genome_to_diffraction.schemas.io import (
    ContractError,
    InputFormat,
    contract_json_schema,
    contract_kinds,
    load_contract,
)
from genome_to_diffraction.status import GenomeToDiffractionError


def _add_contract_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("kind", choices=contract_kinds(), help="contract kind")
    parser.add_argument("input", type=Path, help="JSON, YAML, or supported TSV input")
    parser.add_argument(
        "--format",
        choices=("auto", "json", "yaml", "tsv"),
        default="auto",
        help="input format (default: infer from suffix)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genome-to-diffraction")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG, INFO, WARNING, ERROR, or CRITICAL",
    )
    parser.add_argument(
        "--log-format",
        choices=("human", "json"),
        default="human",
        help="diagnostic log rendering (default: human)",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="disable tqdm progress bars",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema_parser = subparsers.add_parser(
        "schema-check", help="validate repository schemas and fixtures"
    )
    schema_parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )

    contract_parser = subparsers.add_parser(
        "contract", help="validate or canonicalise a versioned contract"
    )
    contract_actions = contract_parser.add_subparsers(
        dest="contract_action", required=True
    )
    validate_parser = contract_actions.add_parser(
        "validate", help="validate a JSON, YAML, or supported TSV contract"
    )
    _add_contract_input(validate_parser)
    canonicalise_parser = contract_actions.add_parser(
        "canonicalise", help="write validated RFC 8785 canonical JSON"
    )
    _add_contract_input(canonicalise_parser)
    canonicalise_parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: standard output)",
    )
    schema_output_parser = contract_actions.add_parser(
        "schema", help="write a Draft 2020-12 JSON Schema for a contract"
    )
    schema_output_parser.add_argument("kind", choices=contract_kinds())
    schema_output_parser.add_argument(
        "--output",
        type=Path,
        help="output path (default: standard output)",
    )

    phenix_parser = subparsers.add_parser(
        "phenix", help="install, verify, or execute the external Phenix runtime"
    )
    phenix_actions = phenix_parser.add_subparsers(dest="phenix_action", required=True)
    install_parser = phenix_actions.add_parser(
        "install", help="install a user-supplied Phenix command-line installer"
    )
    install_parser.add_argument(
        "--installer", type=Path, required=True, help="user-supplied installer file"
    )
    install_parser.add_argument(
        "--installer-sha256",
        required=True,
        help="expected full SHA-256 of the installer file",
    )
    install_parser.add_argument(
        "--prefix",
        type=Path,
        required=True,
        help="new absolute versioned prefix, such as /opt/phenix-2.1-XXXX",
    )
    install_parser.add_argument(
        "--expected-release",
        default="2.1",
        help="required PHENIX_VERSION release family (default: 2.1)",
    )
    install_parser.add_argument(
        "--expected-build", help="optional exact PHENIX_VERSION value"
    )
    install_parser.add_argument(
        "--temp-dir",
        type=Path,
        required=True,
        help="absolute executable temporary directory with at least 25 GiB free",
    )
    install_parser.add_argument(
        "--manifest", type=Path, required=True, help="new manifest output path"
    )
    install_parser.add_argument(
        "--current-link",
        type=Path,
        help="optional controlled symlink updated only after verification",
    )
    install_parser.add_argument(
        "--operator-note",
        action="append",
        default=[],
        help="repeatable provenance note stored in the manifest",
    )
    install_parser.add_argument(
        "--minimum-install-free-gb",
        type=float,
        default=15.0,
        help="minimum installation-filesystem free space (default: 15 GiB)",
    )
    install_parser.add_argument(
        "--minimum-temp-free-gb",
        type=float,
        default=25.0,
        help="minimum temporary-filesystem free space (default: 25 GiB)",
    )
    install_parser.add_argument(
        "--allow-home-root",
        action="store_true",
        help="allow the home root itself as an administrative target",
    )
    install_parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=120.0,
        help="per-command smoke-test timeout (default: 120)",
    )

    verify_parser = phenix_actions.add_parser(
        "verify", help="revalidate a recorded Phenix installation manifest"
    )
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--verification-log", type=Path)
    verify_parser.add_argument("--command-timeout-seconds", type=float, default=120.0)

    recover_parser = phenix_actions.add_parser(
        "recover-failed",
        help="requalify one exact installer-preserved failed Phenix tree",
    )
    recover_parser.add_argument("--failed-prefix", type=Path, required=True)
    recover_parser.add_argument("--prefix", type=Path, required=True)
    recover_parser.add_argument("--failed-manifest", type=Path, required=True)
    recover_parser.add_argument("--failed-manifest-sha256", required=True)
    recover_parser.add_argument("--manifest", type=Path, required=True)
    recover_parser.add_argument("--expected-release", default="2.1")
    recover_parser.add_argument("--expected-build", required=True)
    recover_parser.add_argument(
        "--tool-revision",
        required=True,
        help="full Git SHA of the reviewed recovery implementation",
    )
    recover_parser.add_argument("--current-link", type=Path, required=True)
    recover_parser.add_argument("--command-timeout-seconds", type=float, default=120.0)

    execute_parser = phenix_actions.add_parser(
        "exec", help="execute one command in an isolated verified Phenix shell"
    )
    execute_parser.add_argument("--manifest", type=Path, required=True)
    execute_parser.add_argument(
        "phenix_command",
        nargs=argparse.REMAINDER,
        help="exact command and arguments, conventionally after --",
    )

    database_parser = subparsers.add_parser(
        "databases", help="prepare or verify shared reference databases"
    )
    database_actions = database_parser.add_subparsers(
        dest="database_action", required=True
    )
    prepare_parser = database_actions.add_parser(
        "prepare", help="run explicit idempotent database preparation"
    )
    prepare_parser.add_argument("--database-root", type=Path, required=True)
    prepare_parser.add_argument("--manifest", type=Path, required=True)
    prepare_parser.add_argument("--prepare-pdb-foldseek", action="store_true")
    prepare_parser.add_argument("--prepare-pdb-sequences", action="store_true")
    prepare_parser.add_argument("--prepare-prostt5", action="store_true")
    prepare_parser.add_argument("--initialise-coordinate-cache", action="store_true")
    prepare_parser.add_argument("--verify-esm-atlas-connectivity", action="store_true")
    prepare_parser.add_argument("--verify-only", action="store_true")
    prepare_parser.add_argument("--force-rebuild", action="store_true")
    prepare_parser.add_argument("--full-verify", action="store_true")
    prepare_parser.add_argument(
        "--expected-manifest",
        type=Path,
        help="operator-frozen manifest required by verify-only",
    )
    prepare_parser.add_argument(
        "--expected-manifest-sha256",
        help="trusted SHA-256 of --expected-manifest",
    )
    prepare_parser.add_argument("--threads", type=int, default=4)
    prepare_parser.add_argument(
        "--storage-limit-bytes", type=int, default=DEFAULT_STORAGE_LIMIT_BYTES
    )
    prepare_parser.add_argument(
        "--minimum-free-bytes", type=int, default=DEFAULT_MINIMUM_FREE_BYTES
    )
    prepare_parser.add_argument("--pdb-sequence-url", default=PDB_SEQUENCE_URL)
    prepare_parser.add_argument("--esm-atlas-probe-url", default=ESM_ATLAS_PROBE_URL)

    catalogue_parser = subparsers.add_parser(
        "catalogue", help="normalise trusted protein catalogues"
    )
    catalogue_actions = catalogue_parser.add_subparsers(
        dest="catalogue_action", required=True
    )
    import_parser = catalogue_actions.add_parser(
        "import", help="import, deduplicate, and inventory trusted catalogues"
    )
    import_parser.add_argument(
        "--catalogues", type=Path, required=True, help="catalogue manifest"
    )
    import_parser.add_argument(
        "--config", type=Path, required=True, help="pipeline configuration"
    )
    import_parser.add_argument(
        "--outdir", type=Path, required=True, help="stable output directory"
    )

    diffraction_parser = subparsers.add_parser(
        "diffraction", help="inspect crystallographic diffraction inputs"
    )
    diffraction_actions = diffraction_parser.add_subparsers(
        dest="diffraction_action", required=True
    )
    preflight_parser = diffraction_actions.add_parser(
        "preflight", help="inspect MTZ files and optionally run Phenix Xtriage"
    )
    preflight_parser.add_argument("--crystals", type=Path, required=True)
    preflight_parser.add_argument("--phenix-manifest", type=Path)
    preflight_parser.add_argument("--outdir", type=Path, required=True)
    preflight_parser.add_argument(
        "--skip-xtriage",
        action="store_true",
        help="skip Xtriage and force pass-with-review (testing/preparation only)",
    )
    preflight_parser.add_argument(
        "--xtriage-timeout-seconds", type=float, default=3600.0
    )
    free_r_parser = diffraction_actions.add_parser(
        "generate-free-r",
        help="create one immutable Free-R derivative with verified Phenix",
    )
    free_r_parser.add_argument("--source-mtz", type=Path, required=True)
    free_r_parser.add_argument("--output-mtz", type=Path, required=True)
    free_r_parser.add_argument("--phenix-manifest", type=Path, required=True)
    free_r_parser.add_argument("--command-log", type=Path, required=True)
    free_r_parser.add_argument("--record", type=Path, required=True)
    free_r_parser.add_argument("--test-fraction", type=float, default=0.05)
    free_r_parser.add_argument("--maximum-free-reflections", type=int, default=2000)
    free_r_parser.add_argument("--random-seed", type=int, default=20260801)
    free_r_parser.add_argument("--timeout-seconds", type=float, default=3600.0)

    matthews_parser = subparsers.add_parser(
        "matthews", help="enumerate candidate-specific ASU copy hypotheses"
    )
    matthews_actions = matthews_parser.add_subparsers(
        dest="matthews_action", required=True
    )
    enumerate_parser = matthews_actions.add_parser(
        "enumerate", help="calculate Matthews and soft SDS-PAGE priors"
    )
    enumerate_parser.add_argument("--crystals", type=Path, required=True)
    enumerate_parser.add_argument("--config", type=Path, required=True)
    enumerate_parser.add_argument("--preflight", type=Path, required=True)
    enumerate_parser.add_argument("--sequence-groups", type=Path, required=True)
    enumerate_parser.add_argument("--source-records", type=Path, required=True)
    enumerate_parser.add_argument("--outdir", type=Path, required=True)
    return parser


def _run_contract(args: argparse.Namespace, logger: logging.Logger) -> int:
    if args.contract_action == "schema":
        payload = f"{canonical_json_text(contract_json_schema(args.kind))}\n"
        if args.output is None:
            sys.stdout.write(payload)
        else:
            atomic_write_text(args.output, payload)
            logger.info(
                "wrote contract schema",
                extra={"contract_kind": args.kind, "output": str(args.output)},
            )
        return 0

    model = load_contract(
        args.input,
        args.kind,
        input_format=cast(InputFormat, args.format),
        progress=not args.no_progress,
    )
    if args.contract_action == "validate":
        print(f"Valid {args.kind}: {args.input}")
        return 0

    payload = f"{canonical_json_text(model)}\n"
    if args.output is None:
        sys.stdout.write(payload)
    else:
        atomic_write_text(args.output, payload)
        logger.info(
            "wrote canonical contract",
            extra={"contract_kind": args.kind, "output": str(args.output)},
        )
    return 0


def _run_phenix(args: argparse.Namespace, logger: logging.Logger) -> int:
    gib = 1024**3
    if args.phenix_action == "install":
        request = InstallRequest(
            installer=args.installer,
            installer_sha256=args.installer_sha256,
            installation_prefix=args.prefix,
            expected_release=args.expected_release,
            expected_build=args.expected_build,
            temporary_directory=args.temp_dir,
            manifest_path=args.manifest,
            current_symlink=args.current_link,
            operator_notes=tuple(args.operator_note),
            minimum_install_free_bytes=int(args.minimum_install_free_gb * gib),
            minimum_temporary_free_bytes=int(args.minimum_temp_free_gb * gib),
            allow_home_root=args.allow_home_root,
            progress=not args.no_progress,
            command_timeout_seconds=args.command_timeout_seconds,
        )
        manifest = install_phenix(request)
        print(f"Verified Phenix {manifest.phenix_version}: {args.manifest}")
        return 0
    if args.phenix_action == "verify":
        inspection = verify_manifest(
            args.manifest,
            progress=not args.no_progress,
            timeout_seconds=args.command_timeout_seconds,
            verification_log=args.verification_log,
        )
        print(
            f"Verified Phenix {inspection.phenix_version}: {inspection.phenix_prefix}"
        )
        return 0
    if args.phenix_action == "recover-failed":
        manifest = recover_failed_install(
            RecoveryRequest(
                failed_prefix=args.failed_prefix,
                installation_prefix=args.prefix,
                failed_manifest=args.failed_manifest,
                failed_manifest_sha256=args.failed_manifest_sha256,
                recovered_manifest=args.manifest,
                expected_release=args.expected_release,
                expected_build=args.expected_build,
                tool_revision=args.tool_revision,
                current_symlink=args.current_link,
                progress=not args.no_progress,
                command_timeout_seconds=args.command_timeout_seconds,
            )
        )
        print(f"Recovered Phenix {manifest.phenix_version}: {args.manifest}")
        return 0
    if args.phenix_action == "exec":
        command = list(args.phenix_command)
        if command and command[0] == "--":
            command = command[1:]
        return execute_from_manifest(args.manifest, command)
    raise AssertionError(f"unhandled Phenix action: {args.phenix_action}")


def _run_databases(args: argparse.Namespace) -> int:
    if args.database_action != "prepare":
        raise AssertionError(f"unhandled database action: {args.database_action}")
    manifest = prepare(
        DatabasePreparationRequest(
            database_root=args.database_root,
            manifest_path=args.manifest,
            prepare_pdb_foldseek=args.prepare_pdb_foldseek,
            prepare_pdb_sequences=args.prepare_pdb_sequences,
            prepare_prostt5=args.prepare_prostt5,
            initialise_coordinate_cache=args.initialise_coordinate_cache,
            verify_esm_atlas_connectivity=args.verify_esm_atlas_connectivity,
            verify_only=args.verify_only,
            force_rebuild=args.force_rebuild,
            full_verify=args.full_verify,
            expected_manifest_path=args.expected_manifest,
            expected_manifest_sha256=args.expected_manifest_sha256,
            storage_limit_bytes=args.storage_limit_bytes,
            minimum_free_bytes=args.minimum_free_bytes,
            threads=args.threads,
            progress=not args.no_progress,
            pdb_sequence_url=args.pdb_sequence_url,
            esm_atlas_probe_url=args.esm_atlas_probe_url,
        )
    )
    print(f"Prepared {len(manifest.resources)} database resources: {args.manifest}")
    return 0


def _run_catalogue(args: argparse.Namespace) -> int:
    if args.catalogue_action != "import":
        raise AssertionError(f"unhandled catalogue action: {args.catalogue_action}")
    result = import_catalogues(
        CatalogueImportRequest(
            catalogue_manifest=args.catalogues,
            pipeline_config=args.config,
            output_directory=args.outdir,
            progress=not args.no_progress,
        )
    )
    print(
        f"Imported {result.manifest.source_record_count} source proteins into "
        f"{result.manifest.sequence_group_count} exact sequence groups: {args.outdir}"
    )
    return 0


def _run_diffraction(args: argparse.Namespace) -> int:
    if args.diffraction_action == "generate-free-r":
        record = generate_free_r(
            FreeRGenerationRequest(
                source_mtz=args.source_mtz,
                output_mtz=args.output_mtz,
                phenix_manifest=args.phenix_manifest,
                command_log=args.command_log,
                record_path=args.record,
                test_fraction=args.test_fraction,
                maximum_free_reflections=args.maximum_free_reflections,
                random_seed=args.random_seed,
                timeout_seconds=args.timeout_seconds,
                progress=not args.no_progress,
            )
        )
        print(
            f"Generated immutable Free-R MTZ {record.generation_id}: {args.output_mtz}"
        )
        return 0
    if args.diffraction_action != "preflight":
        raise AssertionError(f"unhandled diffraction action: {args.diffraction_action}")
    result = preflight_crystals(
        PreflightRequest(
            crystal_manifest=args.crystals,
            output_directory=args.outdir,
            phenix_manifest=args.phenix_manifest,
            skip_xtriage=args.skip_xtriage,
            progress=not args.no_progress,
            xtriage_timeout_seconds=args.xtriage_timeout_seconds,
        )
    )
    print(f"Preflighted {len(result.records)} MTZ file(s): {args.outdir}")
    return 0


def _run_matthews(args: argparse.Namespace) -> int:
    if args.matthews_action != "enumerate":
        raise AssertionError(f"unhandled Matthews action: {args.matthews_action}")
    result = enumerate_matthews(
        MatthewsRequest(
            crystal_manifest=args.crystals,
            pipeline_config=args.config,
            preflight_jsonl=args.preflight,
            sequence_groups_jsonl=args.sequence_groups,
            source_records_jsonl=args.source_records,
            output_directory=args.outdir,
            progress=not args.no_progress,
        )
    )
    print(f"Enumerated {len(result.hypotheses)} Matthews hypotheses: {args.outdir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        level = parse_log_level(args.log_level)
    except ValueError as level_error:
        parser.error(str(level_error))
    logger = configure_logging(level=level, log_format=args.log_format)

    try:
        if args.command == "schema-check":
            errors = validate_repository(args.repository)
            if errors:
                for schema_error in errors:
                    logger.error(
                        "schema validation failed", extra={"error": schema_error}
                    )
                return 1
            print("All schemas, fixtures, and review TSV contracts are valid.")
            return 0
        if args.command == "contract":
            return _run_contract(args, logger)
        if args.command == "phenix":
            return _run_phenix(args, logger)
        if args.command == "databases":
            return _run_databases(args)
        if args.command == "catalogue":
            return _run_catalogue(args)
        if args.command == "diffraction":
            return _run_diffraction(args)
        if args.command == "matthews":
            return _run_matthews(args)
    except PhenixInstallCommandError as error:
        logger.error(
            "Phenix installer command failed",
            extra={"error": str(error), "exit_status": error.returncode},
        )
        return error.returncode
    except (
        ContractError,
        GenomeToDiffractionError,
        OSError,
        ValueError,
    ) as error:
        logger.error("command failed", extra={"error": str(error)})
        return 1
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
