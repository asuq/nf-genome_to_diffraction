"""Exercise the fixed remote scripts with real Git and fake Slurm commands."""

import base64
import hashlib
import io
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from genome_to_diffraction.checksums import atomic_write_json
from genome_to_diffraction.hpc.unknown_inputs import (
    UNKNOWN_DISCOVERY_SPEC_RELATIVE,
    build_unknown_discovery_input_bundle,
)
from genome_to_diffraction.hpc.unknown_single_inputs import (
    UNKNOWN_SINGLE_SPEC_RELATIVE,
    build_unknown_single_component_input_bundle,
)
from tests.support.unknown_pass1_fixture import (
    materialise_unknown_pass1_public_fixture,
)

REPOSITORY = Path(__file__).resolve().parents[2]
RUN_ID = "gtd-smoke-20260802T120000Z-0123456789ab-01234567"
SECOND_RUN_ID = "gtd-smoke-20260802T120001Z-0123456789ab-01234568"
P0_RUN_ID = "gtd-p0-20260802T120000Z-0123456789ab-01234567"
P1_RUN_ID = "gtd-p1-20260802T120000Z-0123456789ab-01234567"
P2_RUN_ID = "gtd-p2-20260802T120000Z-0123456789ab-01234567"
P2_DIVERSE_RUN_ID = "gtd-p2-diverse-20260802T120000Z-0123456789ab-01234567"
P2_CONTROL_RUN_ID = "gtd-p2-control-20260802T120000Z-0123456789ab-01234567"
HETEROMER_RUN_ID = "gtd-heteromer-smoke-20260802T120000Z-0123456789ab-01234567"
PHASE3_PHENIX_PROBE_RUN_ID = (
    "gtd-phase3-phenix-probe-20260802T120000Z-0123456789ab-01234567"
)
PHASE3_NETWORK_PROBE_RUN_ID = (
    "gtd-phase3-network-probe-20260802T120000Z-0123456789ab-01234567"
)
UNKNOWN_DISCOVERY_RUN_ID = (
    "gtd-unknown-discovery-20260802T120000Z-0123456789ab-01234567"
)
UNKNOWN_SCREEN_RUN_ID = "gtd-unknown-screen-20260802T120001Z-0123456789ab-01234568"
UNKNOWN_SINGLE_RUN_ID = (
    "gtd-unknown-single-component-20260802T120002Z-0123456789ab-01234569"
)
CONTROL_MATRIX_RUN_ID = "gtd-control-matrix-20260802T120000Z-0123456789ab-01234567"
M6_INPUTS_RUN_ID = "gtd-m6-inputs-20260802T120000Z-0123456789ab-01234567"
M6_NEXTFLOW_SMOKE_RUN_ID = (
    "gtd-m6-nextflow-smoke-20260802T120000Z-0123456789ab-01234567"
)
M6_OPERATIONAL_RUN_ID = "gtd-m6-operational-20260802T120000Z-0123456789ab-01234567"
DATABASE_RUN_ID = "gtd-database-20260802T120000Z-0123456789ab-01234567"
T12_RUN_ID = "gtd-t12-20260802T120000Z-0123456789ab-01234567"
OWNER_ID = "1" * 32


@pytest.fixture(autouse=True)
def _restore_test_tree_permissions(tmp_path: Path) -> Iterator[None]:
    """Make immutable fake checkouts removable after each integration test."""

    yield
    for directory, subdirectories, files in os.walk(tmp_path):
        directory_path = Path(directory)
        if not directory_path.is_symlink():
            try:
                directory_path.chmod(0o700)
            except FileNotFoundError:
                continue
        for name in (*subdirectories, *files):
            path = directory_path / name
            if not path.is_symlink():
                try:
                    path.chmod(0o700)
                except FileNotFoundError:
                    continue


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    input_data: bytes | None = None,
    close_stdin: bool = False,
    success: bool = True,
    timeout_seconds: float = 30.0,
) -> subprocess.CompletedProcess[bytes]:
    try:
        if close_stdin:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                check=False,
                capture_output=True,
                timeout=timeout_seconds,
            )
        else:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                input=input_data,
                check=False,
                capture_output=True,
                timeout=timeout_seconds,
            )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            f"command timed out after {timeout_seconds} seconds: {command}\n"
            f"stdout={error.stdout!r}\nstderr={error.stderr!r}"
        ) from error
    if success and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {command}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
    if not success and result.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {command}")
    return result


def test_run_times_out_blocking_command(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match=r"command timed out after 0\.1 seconds"):
        _run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            timeout_seconds=0.1,
        )


def _git(repository: Path, *arguments: str) -> str:
    return _run(["git", *arguments], cwd=repository).stdout.decode().strip()


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _decode_protocol(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in payload.splitlines():
        key, encoded = line.split(b"\t", maxsplit=1)
        result[key.decode()] = base64.b64decode(encoded).decode()
    return result


def _prepare_git_repositories(root: Path) -> tuple[Path, str]:
    helper = root / "helper"
    helper.mkdir()
    _git(helper, "init", "-q")
    _git(helper, "config", "user.name", "Test")
    _git(helper, "config", "user.email", "test@example.invalid")
    (helper / "README.md").write_text("helper\n", encoding="utf-8")
    _git(helper, "add", "README.md")
    _git(helper, "commit", "-q", "-m", "helper")

    source = root / "source-origin"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "branch", "-M", "main")
    _git(source, "config", "user.name", "Test")
    _git(source, "config", "user.email", "test@example.invalid")
    (source / "pixi.lock").write_text("locked test environment\n", encoding="utf-8")
    bootstrap = source / "bootstrap"
    bootstrap.mkdir()
    for name in (
        "nf-gtd-hpc-remote",
        "nf-gtd-hpc-smoke-job",
        "nf-gtd-hpc-recover-tools",
        "nf-gtd-worker-offline-shell",
    ):
        shutil.copy2(REPOSITORY / "bootstrap" / name, bootstrap / name)
        (bootstrap / name).chmod(0o755)
    shutil.copy2(REPOSITORY / "qualification.nf", source / "qualification.nf")
    shutil.copytree(REPOSITORY / "src", source / "src")
    conf = source / "conf"
    conf.mkdir()
    shutil.copy2(REPOSITORY / "conf/marmic.config", conf / "marmic.config")
    qualification_workflows = source / "workflows" / "qualification"
    qualification_workflows.mkdir(parents=True)
    shutil.copy2(
        REPOSITORY / "workflows/qualification/phase3_network_probe.nf",
        qualification_workflows / "phase3_network_probe.nf",
    )
    m6_benchmarks = source / "benchmarks" / "m6"
    m6_benchmarks.mkdir(parents=True)
    for name in (
        "execution-nextflow-v1.yaml",
        "execution-nextflow-marmic-v1.yaml",
        "protocol.yaml",
    ):
        shutil.copy2(REPOSITORY / "benchmarks" / "m6" / name, m6_benchmarks / name)
    controls = source / "benchmarks" / "public-controls"
    controls.mkdir(parents=True)
    shutil.copy2(
        REPOSITORY / "benchmarks/public-controls/pdb_8oox.yaml",
        controls / "pdb_8oox.yaml",
    )
    shutil.copy2(
        REPOSITORY / "benchmarks/public-controls/pdb_8oox_first_copy_controls.yaml",
        controls / "pdb_8oox_first_copy_controls.yaml",
    )
    shutil.copy2(
        REPOSITORY / "benchmarks/public-controls/afdb_accessions.tsv",
        controls / "afdb_accessions.tsv",
    )
    _git(
        source,
        "add",
        "pixi.lock",
        "bootstrap",
        "qualification.nf",
        "src",
        "conf",
        "workflows",
        "benchmarks",
    )
    _git(
        source,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(helper),
        "external/nf-helper",
    )
    _git(source, "commit", "-q", "-m", "source")
    return source, _git(source, "rev-parse", "HEAD")


def _prepare_remote_layout(tmp_path: Path) -> tuple[Path, Path, dict[str, str], str]:
    root = tmp_path / "remote-root"
    tooling = root / "_tooling"
    mirror_parent = root / "_cache" / "git"
    tooling.mkdir(parents=True)
    mirror_parent.mkdir(parents=True)
    (root / "_locks").mkdir()
    (root / "runs").mkdir()

    dispatcher = tooling / "nf-gtd-hpc-remote"
    smoke_job = tooling / "nf-gtd-hpc-smoke-job"
    shutil.copy2(REPOSITORY / "bootstrap" / dispatcher.name, dispatcher)
    shutil.copy2(REPOSITORY / "bootstrap" / smoke_job.name, smoke_job)
    dispatcher.chmod(0o755)
    smoke_job.chmod(0o755)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    python = shlex.quote(sys.executable)
    sha256sum = shutil.which("sha256sum")
    assert sha256sum is not None
    fake_stat = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "${FAKE_STAT_DISTINCT:-0}" == 1 && "${1-}" == -c && '
        '"${2-}" == %d ]]; then\n'
        '  case "${3-}" in\n'
        "    *db-scratch*|*/nf-gtd-database-parent-*) echo 222; exit 0 ;;\n"
        "    *database-admin/databases*) echo 111; exit 0 ;;\n"
        "  esac\n"
        "fi\n"
        'if [[ "${1-}" == -c ]]; then\n'
        '  case "${2-}" in\n'
        f"    %a) exec {python} -c 'import os,stat,sys; "
        'print(format(stat.S_IMODE(os.lstat(sys.argv[1]).st_mode), "o"))\' '
        '"${3-}" ;;\n'
        f"    %d) exec {python} -c 'import os,sys; "
        'print(os.stat(sys.argv[1]).st_dev)\' "${3-}" ;;\n'
        f"    %s) exec {python} -c 'import os,sys; "
        'print(os.stat(sys.argv[1]).st_size)\' "${3-}" ;;\n'
        f"    %h) exec {python} -c 'import os,sys; "
        'print(os.stat(sys.argv[1]).st_nlink)\' "${3-}" ;;\n'
        "  esac\n"
        "fi\n"
        "exit 2\n"
    )
    _write_executable(fake_bin / "stat", fake_stat)
    pixi = fake_bin / "pixi"
    _write_executable(
        pixi,
        "#!/usr/bin/env bash\n"
        'case "${1-}" in\n'
        '  --version) echo "pixi ${FAKE_PIXI_VERSION:-0.76.2}" ;;\n'
        "  install)\n"
        '    [[ "${FAKE_PIXI_INSTALL_FAIL:-0}" != 1 ]] || exit 4\n'
        "    previous=\n"
        "    manifest=\n"
        '    for argument in "$@"; do\n'
        '      [[ "$previous" != --manifest-path ]] || manifest="$argument"\n'
        '      previous="$argument"\n'
        "    done\n"
        '    if [[ -n "$manifest" ]]; then\n'
        '      env_root="$(dirname "$manifest")/.pixi/envs/hpc"\n'
        '      env_bin="$env_root/bin"\n'
        '      mkdir -p "$env_bin" "$env_root/lib/jvm/bin"\n'
        "      cat > \"$env_bin/genome-to-diffraction\" <<'FAKE_GTD'\n"
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '[[ "${FAKE_DATABASE_SOURCE_FAIL:-0}" != 1 ]] || exit 12\n'
        "mode=\n"
        "previous=\n"
        "output=\n"
        "outdir=\n"
        "refreshed=\n"
        "verification_log=\n"
        "protocol=\n"
        "control_6rtz_preparation=\n"
        "control_3u7q_preparation=\n"
        "catalogue_sequence_groups=\n"
        "provider_plan=\n"
        "provider_entry=\n"
        "partner_plan=\n"
        "crystal_id=\n"
        "search_id=\n"
        "phaser_version=\n"
        "parent_model_identity_fraction=\n"
        "parent_model_uncertainty_source=\n"
        'case " $* " in\n'
        '  *" catalogue import "*) mode=catalogue ;;\n'
        '  *" structure-search resolve-provider-plan "*) mode=provider_plan ;;\n'
        '  *" structure-search afdb-exact "*) mode=afdb ;;\n'
        '  *" structure-search pdb-sequence "*) mode=pdb ;;\n'
        '  *" structure-search register-pdb-coordinates "*) mode=register ;;\n'
        '  *" structure-search validate-phase3-provider-discovery-package "*) '
        "mode=provider_discovery_validate ;;\n"
        '  *" structure-search stage-phase3-provider-coordinates "*) '
        "mode=provider_login_stage ;;\n"
        '  *" structure-search validate-phase3-provider-login-stage "*) '
        "mode=provider_login_validate ;;\n"
        '  *" benchmark prepare-public-control "*) mode=public_control ;;\n'
        '  *" benchmark prepare-6rtz-heteromer-control "*) mode=heteromer ;;\n'
        '  *" benchmark prepare-3u7q-heteromer-control "*) '
        "mode=heteromer_multicopy ;;\n"
        '  *" benchmark prepare-9ecn-phase3-control "*) '
        "mode=heteromer_phase3 ;;\n"
        '  *" benchmark run-9ecn-phase3-control "*) '
        "mode=heteromer_phase3_run ;;\n"
        '  *" benchmark prepare-6rtz-partner-catalogue "*) '
        "mode=heteromer_catalogue ;;\n"
        '  *" benchmark prepare-heteromer-control-slice "*) '
        "mode=heteromer_p6 ;;\n"
        '  *" benchmark assess-heteromer-control-slice "*) '
        "mode=heteromer_p6_assess ;;\n"
        '  *" benchmark approve-6rtz-parent "*) mode=heteromer_review ;;\n'
        '  *" phenix refresh-manifest "*) mode=phenix_refresh ;;\n'
        '  *" phenix probe-phaser-interface "*) mode=phenix_interface ;;\n'
        '  *" phenix verify "*) mode=phenix_verify ;;\n'
        '  *" diffraction preflight "*) mode=preflight ;;\n'
        '  *" matthews enumerate "*) mode=matthews ;;\n'
        '  *" ranking approved-partner-plan "*) mode=partner_plan ;;\n'
        '  *" mr first-copy "*) mode=first_copy ;;\n'
        '  *" mr collect-per-placement "*) mode=placement_collect ;;\n'
        '  *" mr approved-partner "*) mode=partner ;;\n'
        '  *" mr search-partner "*) mode=partner ;;\n'
        '  *" mr planned-partner "*) mode=partner ;;\n'
        '  *" mr summarize-partners "*) mode=partner_summary ;;\n'
        '  *" databases stage-sources "*) mode=database ;;\n'
        "esac\n"
        'for argument in "$@"; do\n'
        '  [[ "$previous" != --manifest ]] || output="$argument"\n'
        '  [[ "$previous" != --outdir ]] || outdir="$argument"\n'
        '  [[ "$previous" != --output-directory ]] || outdir="$argument"\n'
        '  [[ "$previous" != --output ]] || refreshed="$argument"\n'
        '  [[ "$previous" != --crystal-id ]] || crystal_id="$argument"\n'
        '  [[ "$previous" != --search-id ]] || search_id="$argument"\n'
        '  [[ "$previous" != --phaser-version ]] || phaser_version="$argument"\n'
        '  [[ "$previous" != --parent-model-identity-fraction ]] || '
        'parent_model_identity_fraction="$argument"\n'
        '  [[ "$previous" != --parent-model-uncertainty-source ]] || '
        'parent_model_uncertainty_source="$argument"\n'
        '  [[ "$previous" != --verification-log ]] || verification_log="$argument"\n'
        '  [[ "$previous" != --protocol ]] || protocol="$argument"\n'
        '  [[ "$previous" != --control-6rtz-preparation ]] || '
        'control_6rtz_preparation="$argument"\n'
        '  [[ "$previous" != --control-3u7q-preparation ]] || '
        'control_3u7q_preparation="$argument"\n'
        '  [[ "$previous" != --catalogue-sequence-groups ]] || '
        'catalogue_sequence_groups="$argument"\n'
        '  [[ "$previous" != --provider-plan ]] || provider_plan="$argument"\n'
        '  [[ "$previous" != --provider-entry ]] || provider_entry="$argument"\n'
        '  [[ "$previous" != --partner-plan ]] || partner_plan="$argument"\n'
        '  previous="$argument"\n'
        "done\n"
        'if [[ "$mode" == catalogue ]]; then\n'
        '  mkdir -p "$outdir"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/catalogue_import_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/sequence_groups.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/source_records.jsonl"\n'
        'elif [[ "$mode" == provider_discovery_validate || '
        '"$mode" == provider_login_validate ]]; then\n'
        "  :\n"
        'elif [[ "$mode" == provider_login_stage ]]; then\n'
        '  mkdir -p "$outdir/pdb_coordinate_registration" '
        '"$outdir/afdb_exact_search" "$outdir/esm_atlas_search"\n'
        '  printf \'{"schema_version":"2.0",'
        '"preparation_id":"providerstage_stub"}\\n\' '
        '> "$outdir/provider_preparation.json"\n'
        'elif [[ "$mode" == provider_plan ]]; then\n'
        '  [[ "${FAKE_PROVIDER_PLAN_FAIL:-0}" != 1 ]] || exit 17\n'
        '  mkdir -p "$outdir/entries"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/provider_plan.json"\n'
        "  for provider in afdb_exact esm_atlas foldseek_prostt5_pdb "
        "pdb_sequence; do\n"
        '    printf \'{"schema_version":"1.0","provider":"%s"}\\n\' '
        '"$provider" > "$outdir/entries/$provider.json"\n'
        "  done\n"
        'elif [[ "$mode" == afdb ]]; then\n'
        '  [[ -f "$provider_plan" && -f "$provider_entry" ]] || exit 18\n'
        '  [[ "${FAKE_AFDB_PREFETCH_FAIL:-0}" != 1 ]] || exit 13\n'
        '  mkdir -p "$outdir/raw"\n'
        '  printf \'{"schema_version":"1.0","coordinate_source_count":1}\\n\' '
        '> "$outdir/search_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/search_results.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/structural_hits.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/coordinate_sources.jsonl"\n'
        "  printf 'fake login-node HTTP provenance\\n' > \"$outdir/raw/http.log\"\n"
        'elif [[ "$mode" == pdb ]]; then\n'
        '  [[ -f "$provider_plan" && -f "$provider_entry" ]] || exit 18\n'
        '  [[ "${FAKE_PDB_SEARCH_FAIL:-0}" != 1 ]] || exit 14\n'
        "  command -v mmseqs >/dev/null || exit 16\n"
        '  mkdir -p "$outdir/raw"\n'
        '  printf \'{"schema_version":"1.0","hit_count":1}\\n\' '
        '> "$outdir/search_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/search_results.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/structural_hits.jsonl"\n'
        "  printf 'fake direct PDB search\\n' > \"$outdir/raw/mmseqs.log\"\n"
        'elif [[ "$mode" == register ]]; then\n'
        '  [[ "${FAKE_PDB_REGISTRATION_FAIL:-0}" != 1 ]] || exit 15\n'
        '  mkdir -p "$outdir"\n'
        '  printf \'{"schema_version":"1.0","coordinate_id":"coord_test"}\\n\' '
        '> "$outdir/coordinate_sources.jsonl"\n'
        '  printf \'{"schema_version":"1.0","mapping_id":"mapping_test"}\\n\' '
        '> "$outdir/coordinate_hit_mappings.jsonl"\n'
        '  printf \'{"schema_version":"1.0","selected_mapping_count":1}\\n\' '
        '> "$outdir/registration_manifest.json"\n'
        'elif [[ "$mode" == database ]]; then\n'
        '  [[ -n "$output" ]] || exit 9\n'
        '  mkdir -p "$(dirname "$output")"\n'
        '  printf \'{"schema_version":"1.0","status":"ready",'
        '"bundle_id":"dbsrc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        'aaaaaaaaaaaaaaaa","created_at":"2026-08-09T00:00:00Z",'
        '"resources":[]}\\n\' > "$output"\n'
        'elif [[ "$mode" == public_control ]]; then\n'
        '  mkdir -p "$outdir/manifests" "$outdir/derived" "$outdir/models"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/manifests/preparation.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/manifests/catalogues.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/manifests/crystals.json"\n'
        "  printf 'fake mtz\\n' > "
        '"$outdir/derived/8OOX-autoproc-deposited.mtz"\n'
        "  printf 'fake pdb\\n' > "
        '"$outdir/models/8OOW-chain-A-polymer.pdb"\n'
        'elif [[ "$mode" == heteromer ]]; then\n'
        '  mkdir -p "$outdir/derived" "$outdir/models"\n'
        "  parent_seq=\"seq_$(printf 'a%.0s' {1..64})\"\n"
        "  partner_seq=\"seq_$(printf 'b%.0s' {1..64})\"\n"
        "  hypothesis=\"mrhyp_$(printf 'c%.0s' {1..64})\"\n"
        "  preparation_id=\"heteromerprep_$(printf '1%.0s' {1..64})\"\n"
        '  printf \'{"preparation_id":"%s","control_key":"A01",'
        '"crystal_id":"6RTZ","composition":{"A":1,"B":1},'
        '"parent_hypothesis_id":"%s",'
        '"parent_sequence_group_id":"%s",'
        '"partner_sequence_group_id":"%s"}\\n\' '
        '"$preparation_id" "$hypothesis" "$parent_seq" "$partner_seq" '
        '> "$outdir/preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/crystals.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/sequence_groups.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/model_preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/mr_hypotheses.jsonl"\n'
        '  printf "fake 6RTZ mtz\\n" > "$outdir/derived/6RTZ.mtz"\n'
        '  printf "fake A pdb\\n" > "$outdir/models/component_A.pdb"\n'
        '  printf "fake B pdb\\n" > "$outdir/models/component_B.pdb"\n'
        'elif [[ "$mode" == heteromer_multicopy ]]; then\n'
        '  mkdir -p "$outdir/derived" "$outdir/models"\n'
        "  parent_seq=\"seq_$(printf 'd%.0s' {1..64})\"\n"
        "  partner_seq=\"seq_$(printf 'e%.0s' {1..64})\"\n"
        "  hypothesis=\"mrhyp_$(printf 'f%.0s' {1..64})\"\n"
        "  preparation_id=\"heteromerprep_$(printf '2%.0s' {1..64})\"\n"
        '  printf "fake 3U7Q mtz\\n" > "$outdir/derived/3U7Q.mtz"\n'
        '  printf "fake A2 pdb\\n" > "$outdir/models/component_A.pdb"\n'
        '  printf "fake B2 pdb\\n" > "$outdir/models/component_B.pdb"\n'
        "  partner_sha=\"$(printf '0%.0s' {1..64})\"\n"
        '  printf \'{"adapter_version":"3u7q-fixed-two-a-two-b-inputs-v1",'
        '"preparation_id":"%s","control_key":"A03",'
        '"crystal_id":"3U7Q","composition":{"A":2,"B":2},'
        '"parent_hypothesis_id":"%s","parent_sequence_group_id":"%s",'
        '"partner_sequence_group_id":"%s","partner_model_identity_fraction":1.0,'
        '"files":{"partner_model":{"sha256":"%s"}}}\\n\' '
        '"$preparation_id" "$hypothesis" "$parent_seq" "$partner_seq" '
        '"$partner_sha" '
        '> "$outdir/preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/crystals.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/sequence_groups.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/model_preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/mr_hypotheses.jsonl"\n'
        'elif [[ "$mode" == heteromer_phase3 ]]; then\n'
        '  mkdir -p "$outdir/derived" "$outdir/models"\n'
        '  printf \'{"adapter_version":"9ecn-fixed-two-a-two-b-two-c-inputs-v1",'
        '"crystal_id":"9ECN","composition":{"A":2,"B":2,"C":2}}\\n\' '
        '> "$outdir/preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/crystals.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/sequence_groups.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/model_preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/mr_hypotheses.jsonl"\n'
        '  printf "fake 9ECN mtz\\n" > "$outdir/derived/9ECN.mtz"\n'
        '  printf "fake A3 pdb\\n" > "$outdir/models/component_A.pdb"\n'
        '  printf "fake B3 pdb\\n" > "$outdir/models/component_B.pdb"\n'
        '  printf "fake C3 pdb\\n" > "$outdir/models/component_C.pdb"\n'
        'elif [[ "$mode" == heteromer_phase3_run ]]; then\n'
        "  paths=(provenance/preparation_manifest.json "
        "provenance/phenix_manifest.json preflight/mtz_preflight.jsonl "
        "preflight/xtriage/9ECN.log parent_A/normalised_mr_result.json "
        "parent_A/phaser_command.json parent_A/PHASER.log "
        "parent_A/PHASER.1.pdb partner_B/partner_search_result.json "
        "partner_B/phaser_command.json partner_B/PHASER.log "
        "partner_B/component_A.pdb partner_B/component_B.pdb "
        "partner_B/phaser_per_placement_inventory.json component_C_input.json "
        "component_C/component_search_result.json component_C/phaser_command.json "
        "component_C/PHASER.log component_C/component_A.pdb "
        "component_C/component_B.pdb component_C/component_C.pdb "
        "component_C/phaser_per_placement_inventory.json)\n"
        '  for relative in "${paths[@]}"; do\n'
        '    directory="${relative%/*}"\n'
        '    [[ "$directory" == "$relative" ]] || mkdir -p "$outdir/$directory"\n'
        '    printf "fake 9ECN retained evidence\\n" > "$outdir/$relative"\n'
        "  done\n"
        '  printf \'{"adapter_version":"9ecn-phase3-depth-three-control-v1",'
        '"control":"9ECN_McrA_McrB_McrG_2A_2B_2C",'
        '"gate_passed":true,"component_copy_counts":{"A":2,"B":2,"C":2},'
        '"exact_identity_claimed_by_search":false,'
        '"complete_composition_claimed_by_search":false}\\n\' '
        '> "$outdir/phase3-9ecn-control-summary.json"\n'
        '  (cd "$outdir" && sha256sum "${paths[@]}" '
        "phase3-9ecn-control-summary.json) "
        '> "$outdir/phase3-9ecn-control-checksums.sha256"\n'
        'elif [[ "$mode" == heteromer_catalogue ]]; then\n'
        '  mkdir -p "$outdir/sources" '
        '"$outdir/partner_model_registry/models"\n'
        "  parent_seq=\"seq_$(printf 'a%.0s' {1..64})\"\n"
        "  partner_seq=\"seq_$(printf 'b%.0s' {1..64})\"\n"
        "  model_id=\"model_$(printf '7%.0s' {1..64})\"\n"
        '  printf \'{"protein_record_count":1846,'
        '"parent_sequence_group_id":"%s","partner_sequence_group_id":"%s",'
        '"partner_model_id":"%s"}\\n\' '
        '"$parent_seq" "$partner_seq" "$model_id" '
        '> "$outdir/preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/catalogues.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/pipeline_config.json"\n'
        '  printf ">fake\\nMAAA\\n" > '
        '"$outdir/sources/GCF_000008545.1_protein.faa"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/partner_model_registry/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/partner_model_registry/model_preparation_manifest.json"\n'
        '  printf "ATOM\\n" > '
        '"$outdir/partner_model_registry/models/partner.pdb"\n'
        'elif [[ "$mode" == heteromer_p6 ]]; then\n'
        '  mkdir -p "$outdir/missing_partner_model_registry/models" '
        '"$outdir/wrong_partner"\n'
        "  parent_seq=\"seq_$(printf 'a%.0s' {1..64})\"\n"
        "  wrong_seq=\"seq_$(printf 'e%.0s' {1..64})\"\n"
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/missing_partner_model_registry/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/missing_partner_model_registry/model_preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/wrong_partner/sequence_groups.jsonl"\n'
        '  printf "ATOM\\n" > "$outdir/wrong_partner/model.pdb"\n'
        '  printf "ATOM parent\\n" > "$outdir/missing-parent.pdb"\n'
        '  missing_model_sha="$(sha256sum "$outdir/missing-parent.pdb" '
        "| awk '{print $1}')\"\n"
        '  missing_model_relative="missing_partner_model_registry/models/'
        '${missing_model_sha}.pdb"\n'
        '  mv "$outdir/missing-parent.pdb" '
        '"$outdir/$missing_model_relative"\n'
        '  wrong_model_sha="$(sha256sum "$outdir/wrong_partner/model.pdb" '
        "| awk '{print $1}')\"\n"
        '  protocol_sha="$(sha256sum "$protocol" | awk \'{print $1}\')"\n'
        '  source_6_sha="$(sha256sum "$control_6rtz_preparation" '
        "| awk '{print $1}')\"\n"
        '  source_3_sha="$(sha256sum "$control_3u7q_preparation" '
        "| awk '{print $1}')\"\n"
        '  catalogue_sha="$(sha256sum "$catalogue_sequence_groups" '
        "| awk '{print $1}')\"\n"
        "  universe_sha=\"$(printf '6%.0s' {1..64})\"\n"
        '  [[ "${FAKE_P6_PROVENANCE_MISMATCH:-0}" != 1 ]] || '
        "protocol_sha=\"$(printf '0%.0s' {1..64})\"\n"
        "  scope_id=\"componentscope_$(printf '3%.0s' {1..64})\"\n"
        '  printf \'{"schema_version":"1.0","decision_id":"%s",'
        '"target_key":"A04","crystal_id":"9ECN",'
        '"protocol_id":"m6-frozen-v1","protocol_sha256":"%s",'
        '"observed_distinct_component_count":3,'
        '"supported_distinct_component_count":2,'
        '"status":"unsupported_component_count",'
        '"retain_partial_a_b_evidence":true,'
        '"complete_composition_claim_eligible":false}\\n\' '
        '"$scope_id" "$protocol_sha" > "$outdir/component_scope_decision.json"\n'
        '  missing_models_sha="$(sha256sum '
        '"$outdir/missing_partner_model_registry/processed_models.jsonl" '
        "| awk '{print $1}')\"\n"
        '  missing_manifest_sha="$(sha256sum '
        '"$outdir/missing_partner_model_registry/model_preparation_manifest.json" '
        "| awk '{print $1}')\"\n"
        '  wrong_groups_sha="$(sha256sum '
        '"$outdir/wrong_partner/sequence_groups.jsonl" '
        "| awk '{print $1}')\"\n"
        '  scope_sha="$(sha256sum "$outdir/component_scope_decision.json" '
        "| awk '{print $1}')\"\n"
        '  missing_models_size="$(wc -c < '
        '"$outdir/missing_partner_model_registry/processed_models.jsonl")"\n'
        '  missing_manifest_size="$(wc -c < '
        '"$outdir/missing_partner_model_registry/model_preparation_manifest.json")"\n'
        '  missing_model_size="$(wc -c < "$outdir/$missing_model_relative")"\n'
        '  wrong_groups_size="$(wc -c < '
        '"$outdir/wrong_partner/sequence_groups.jsonl")"\n'
        '  wrong_model_size="$(wc -c < "$outdir/wrong_partner/model.pdb")"\n'
        '  scope_size="$(wc -c < "$outdir/component_scope_decision.json")"\n'
        '  printf \'{"adapter_version":"heteromer-p6-control-slice-v2",'
        '"protocol":{"protocol_id":"m6-frozen-v1","sha256":"%s"},'
        '"source_preparations":{"6RTZ":{"preparation_id":"heteromerprep_%s",'
        '"manifest_sha256":"%s"},"3U7Q":{"preparation_id":"heteromerprep_%s",'
        '"manifest_sha256":"%s"}},'
        '"catalogue_sequence_groups":{"sha256":"%s",'
        '"sequence_group_count":1846,"candidate_sequence_group_count":1845,'
        '"candidate_universe_sha256":"%s"},'
        '"missing_partner":{"parent_sequence_group_id":"%s",'
        '"expected_candidate_count":1845,"candidate_universe_sha256":"%s"},'
        '"wrong_partner":{"parent_sequence_group_id":"%s",'
        '"partner_sequence_group_id":"%s",'
        '"partner_model_sha256":"%s"},'
        '"unsupported_component_control":{"scope_decision_id":"%s"},'
        '"files":{"missing_processed_models":{"path":"missing_partner_model_registry/'
        'processed_models.jsonl","sha256":"%s","size_bytes":%s},'
        '"missing_model_manifest":{"path":"missing_partner_model_registry/'
        'model_preparation_manifest.json","sha256":"%s","size_bytes":%s},'
        '"missing_parent_model":{"path":"%s","sha256":"%s",'
        '"size_bytes":%s},"wrong_sequence_groups":{"path":"wrong_partner/'
        'sequence_groups.jsonl","sha256":"%s","size_bytes":%s},'
        '"wrong_partner_model":{"path":"wrong_partner/model.pdb",'
        '"sha256":"%s","size_bytes":%s},'
        '"component_scope_decision":{"path":"component_scope_decision.json",'
        '"sha256":"%s","size_bytes":%s}}}\\n\' '
        '"$protocol_sha" "$(printf \'1%.0s\' {1..64})" "$source_6_sha" '
        '"$(printf \'2%.0s\' {1..64})" "$source_3_sha" '
        '"$catalogue_sha" "$universe_sha" "$parent_seq" "$universe_sha" '
        '"$parent_seq" "$wrong_seq" "$wrong_model_sha" '
        '"$scope_id" '
        '"$missing_models_sha" "$missing_models_size" '
        '"$missing_manifest_sha" "$missing_manifest_size" '
        '"$missing_model_relative" "$missing_model_sha" "$missing_model_size" '
        '"$wrong_groups_sha" "$wrong_groups_size" '
        '"$wrong_model_sha" "$wrong_model_size" "$scope_sha" "$scope_size" '
        '> "$outdir/preparation_manifest.json"\n'
        'elif [[ "$mode" == heteromer_p6_assess ]]; then\n'
        '  [[ -n "$refreshed" ]] || exit 20\n'
        '  mkdir -p "$(dirname "$refreshed")"\n'
        '  assessments="$(dirname "$refreshed")/'
        'heteromer-composition-assessments.jsonl"\n'
        '  : > "$assessments"\n'
        "  scope_id=\"componentscope_$(printf '3%.0s' {1..64})\"\n"
        "  evidence_sha=\"$(printf '4%.0s' {1..64})\"\n"
        "  case_ids=(6RTZ_positive_1A_1B 3U7Q_positive_2A_2B missing_B "
        "wrong_B homomer_non_regression 9ECN_three_component_boundary)\n"
        "  crystal_ids=(6RTZ 3U7Q 6RTZ 6RTZ 6RTZ 9ECN)\n"
        "  case_kinds=(known_positive_control known_positive_control "
        "missing_partner_control wrong_partner_control homomer_non_regression "
        "component_scope_boundary)\n"
        "  scientific_statuses=(known_control_recovered known_control_recovered "
        "no_partner_attempted search_evidence_only route_non_regression "
        "unsupported_component_count)\n"
        "  for ((i=0; i<6; i++)); do\n"
        "    eligible=false; exact=false; scope=within_supported_component_count\n"
        "    scope_decision=null\n"
        '    [[ "$i" -ge 2 ]] || { eligible=true; exact=true; }\n'
        '    [[ "$i" -ne 5 ]] || { scope=unsupported_component_count; '
        'scope_decision="\\"$scope_id\\""; }\n'
        '    assessment_id="assessment_$(printf \'%064d\' "$((i + 1))")"\n'
        '    printf \'{"schema_version":"1.0","assessment_id":"%s",'
        '"case_id":"%s","crystal_id":"%s","case_kind":"%s",'
        '"execution_status":"completed_hit","placement_observed":true,'
        '"exact_identity_supported":%s,"scope_status":"%s",'
        '"scope_decision_id":%s,"scientific_status":"%s",'
        '"complete_composition_claim_eligible":%s,'
        '"complete_composition_claimed":false,"evidence_sha256":{"result":"%s"}}\\n\' '
        '"$assessment_id" "${case_ids[$i]}" "${crystal_ids[$i]}" '
        '"${case_kinds[$i]}" "$exact" "$scope" "$scope_decision" '
        '"${scientific_statuses[$i]}" "$eligible" "$evidence_sha" '
        '>> "$assessments"\n'
        "  done\n"
        '  assessments_sha="$(sha256sum "$assessments" | awk \'{print $1}\')"\n'
        '  printf \'{"schema_version":"1.0","gate_passed":true,'
        '"composition_assessments_sha256":"%s",'
        '"cases":{"missing_B":{"gate_passed":true,'
        '"assessment":{"complete_composition_claim_eligible":false,'
        '"complete_composition_claimed":false}},'
        '"wrong_B":{"gate_passed":true,'
        '"assessment":{"scientific_status":"search_evidence_only",'
        '"complete_composition_claim_eligible":false,'
        '"complete_composition_claimed":false}},'
        '"9ECN_three_component_boundary":{"gate_passed":true,'
        '"status":"unsupported_component_count",'
        '"assessment":{"scope_decision_id":"%s",'
        '"complete_composition_claim_eligible":false,'
        '"complete_composition_claimed":false}}}}\\n\' '
        '"$assessments_sha" "$scope_id" > "$refreshed"\n'
        'elif [[ "$mode" == heteromer_review ]]; then\n'
        '  mkdir -p "$outdir/mr_seed_review" '
        '"$outdir/approved_mr_seed_stage"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/mr_seed_review/mr_seed_review_manifest.json"\n'
        '  printf "checkpoint\\n" > "$outdir/approved_mr_seeds.tsv"\n'
        '  printf \'{"execution_status":"completed_success"}\\n\' > '
        '"$outdir/approved_mr_seed_stage/live_m4_stage_manifest.json"\n'
        '  printf "seed_solution_id\\n" > '
        '"$outdir/approved_mr_seed_stage/approved_seeds.tsv"\n'
        '  printf \'{"execution_status":"completed_success"}\\n\' > '
        '"$outdir/approved_mr_seed_stage/validated_mr_seed_decisions.json"\n'
        'elif [[ "$mode" == phenix_verify ]]; then\n'
        '  [[ -n "$verification_log" ]] || exit 17\n'
        '  mkdir -p "$(dirname "$verification_log")"\n'
        '  printf "fake Phenix verified\\n" > "$verification_log"\n'
        'elif [[ "$mode" == phenix_refresh ]]; then\n'
        '  [[ -n "$verification_log" && -n "$refreshed" ]] || exit 18\n'
        '  mkdir -p "$(dirname "$verification_log")"\n'
        '  printf "fake Phenix refreshed\\n" > "$verification_log"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$refreshed"\n'
        'elif [[ "$mode" == phenix_interface ]]; then\n'
        '  mkdir -p "$outdir"\n'
        '  printf "phaser { keywords { xyzout { ensemble = False } } }\\n" > '
        '"$outdir/phenix-phaser-show-defaults.txt"\n'
        '  printf \'{"schema_version":"1.0","probe_id":'
        '"phaserinterface_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        '"scientific_execution_performed":false}\\n\' > '
        '"$outdir/phaser-interface-probe.json"\n'
        'elif [[ "$mode" == preflight ]]; then\n'
        '  mkdir -p "$outdir/xtriage"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$outdir/mtz_preflight.jsonl"\n'
        '  printf "fake xtriage\\n" > "$outdir/xtriage/6RTZ.log"\n'
        '  printf "fake xtriage\\n" > "$outdir/xtriage/3U7Q.log"\n'
        'elif [[ "$mode" == matthews ]]; then\n'
        '  mkdir -p "$outdir"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/matthews_hypotheses.jsonl"\n'
        '  printf "stub\\n" > "$outdir/matthews_hypotheses.tsv"\n'
        '  printf "stub\\n" > "$outdir/matthews_hypotheses.parquet"\n'
        '  printf "stub\\n" > "$outdir/matthews_report.md"\n'
        'elif [[ "$mode" == partner_plan ]]; then\n'
        '  mkdir -p "$outdir"\n'
        "  parent_seq=\"seq_$(printf 'a%.0s' {1..64})\"\n"
        "  partner_seq=\"seq_$(printf 'b%.0s' {1..64})\"\n"
        "  model_id=\"model_$(printf '7%.0s' {1..64})\"\n"
        "  candidate_id=\"partnercand_$(printf '8%.0s' {1..64})\"\n"
        "  partner_seq=\"seq_$(printf 'b%.0s' {1..64})\"\n"
        "  plan_id=\"partnerplan_$(printf '9%.0s' {1..64})\"\n"
        '  if [[ "$outdir" == */p6/missing-plan ]]; then\n'
        '    printf \'{"plan_id":"%s","parent_sequence_group_id":"%s",'
        '"candidate_count":1845,'
        '"searchable_candidate_count":0,"selected_attempt_count":0,'
        '"deferred_cap_count":0,"unsearchable_candidate_count":1845,'
        '"candidates":[\' "$plan_id" "$parent_seq" '
        '> "$outdir/partner_search_plan.json"\n'
        '    : > "$outdir/partner_candidates.jsonl"\n'
        "    for ((i=1; i<=1845; i++)); do\n"
        '      suffix="$(printf \'%064d\' "$i")"\n'
        '      row="{\\"candidate_id\\":\\"partnercand_${suffix}\\",'
        '\\"sequence_group_id\\":\\"seq_${suffix}\\",'
        '\\"model_id\\":null,\\"selection_status\\":'
        '\\"unsearchable_no_model\\"}"\n'
        "      [[ \"$i\" -eq 1 ]] || printf ',' "
        '>> "$outdir/partner_search_plan.json"\n'
        '      printf \'%s\' "$row" >> "$outdir/partner_search_plan.json"\n'
        '      printf \'%s\\n\' "$row" >> "$outdir/partner_candidates.jsonl"\n'
        "    done\n"
        "    printf ']}\\n' >> \"$outdir/partner_search_plan.json\"\n"
        '    : > "$outdir/selected_partner_candidate_ids.txt"\n'
        "  else\n"
        '  printf \'{"plan_id":"%s","candidate_count":1845,'
        '"searchable_candidate_count":1,"selected_attempt_count":1,'
        '"deferred_cap_count":0,"unsearchable_candidate_count":1844,'
        '"candidates":[{"candidate_id":"%s","sequence_group_id":"%s",'
        '"model_id":"%s","selection_status":"selected"}]}\\n\' '
        '"$plan_id" "$candidate_id" "$partner_seq" "$model_id" '
        '> "$outdir/partner_search_plan.json"\n'
        '  printf \'{"candidate_id":"%s","sequence_group_id":"%s",'
        '"model_id":"%s","selection_status":"selected"}\\n\' '
        '"$candidate_id" "$partner_seq" "$model_id" '
        '> "$outdir/partner_candidates.jsonl"\n'
        '  printf "%s\\n" "$candidate_id" > '
        '"$outdir/selected_partner_candidate_ids.txt"\n'
        "  fi\n"
        'elif [[ "$mode" == first_copy ]]; then\n'
        '  mkdir -p "$outdir"\n'
        "  placed=1\n"
        '  [[ "$outdir" != */multicopy/* ]] || placed=2\n'
        '  : > "$outdir/PHASER.1.pdb"\n'
        "  for ((i=0; i<placed; i++)); do "
        'printf "REMARK ENSEMBLE parent\\n" >> "$outdir/PHASER.1.pdb"; done\n'
        '  printf "ATOM\\n" >> "$outdir/PHASER.1.pdb"\n'
        '  printf "fake parent mtz\\n" > "$outdir/PHASER.1.mtz"\n'
        '  parent_sha="$(sha256sum "$outdir/PHASER.1.pdb" | awk \'{print $1}\')"\n'
        '  printf \'{"execution_status":"completed_hit","llg":120.0,'
        '"placed_copy_count":%s,"packing_summary":'
        '{"top_solution_packed":true},'
        '"solution_coordinate_path":"PHASER.1.pdb",'
        '"solution_coordinate_sha256":"%s"}\\n\' "$placed" "$parent_sha" '
        '> "$outdir/normalised_mr_result.json"\n'
        '  cp "$outdir/normalised_mr_result.json" '
        '"$outdir/normalised_mr_result.jsonl"\n'
        '  printf \'{"model_identity_percent":35.0,'
        '"model_uncertainty_source":"fake registered parent model identity"}\\n\' '
        '> "$outdir/phaser_command.json"\n'
        '  printf "fake parent log\\n" > "$outdir/PHASER.log"\n'
        '  printf "fake parent capture\\n" > "$outdir/phenix.phaser.capture.log"\n'
        'elif [[ "$mode" == partner ]]; then\n'
        '  if [[ "$crystal_id" == 3U7Q ]]; then\n'
        '    [[ "$parent_model_identity_fraction" == 0.35 ]] || exit 32\n'
        '    [[ "$parent_model_uncertainty_source" == '
        '"fake registered parent model identity" ]] || exit 33\n'
        "  fi\n"
        '  mkdir -p "$outdir"\n'
        "  parent_copies=1\n"
        "  partner_copies=1\n"
        "  search_id=\"partner_$(printf '6%.0s' {1..64})\"\n"
        "  phaser_version=2.1-6048\n"
        "  plan_id=\"partnerplan_$(printf '9%.0s' {1..64})\"\n"
        "  candidate_id=\"partnercand_$(printf '8%.0s' {1..64})\"\n"
        "  partner_seq=\"seq_$(printf 'b%.0s' {1..64})\"\n"
        '  [[ "$outdir" != */multicopy/* ]] || { parent_copies=2; partner_copies=2; }\n'
        '  if [[ "$outdir" == */p6/wrong-partner && '
        '"${FAKE_P6_WRONG_NO_SOLUTION:-0}" == 1 ]]; then\n'
        '    printf \'{"execution_status":"completed_no_hit",'
        '"combined_coordinate_path":null,"combined_coordinate_sha256":null,'
        '"output_mtz_path":null,"output_mtz_sha256":null}\\n\' '
        '> "$outdir/partner_search_result.json"\n'
        "  else\n"
        '    printf "fake combined pdb\\n" > "$outdir/PHASER.1.pdb"\n'
        '    printf "fake combined mtz\\n" > "$outdir/PHASER.1.mtz"\n'
        '    printf "SOLU SET LLG=270 TFZ=12\\n" > "$outdir/PHASER.sol"\n'
        "    placement=1\n"
        '    printf "SOLU 6DIM ENSE fixed_parent EULER %s 0 0 FRAC 0 0 0 BFAC 0\\n" '
        '"$placement" >> "$outdir/PHASER.sol"\n'
        "    for ((i=1; i<=partner_copies; i++)); do\n"
        "      placement=$((placement + 1))\n"
        '      printf "SOLU 6DIM ENSE search_partner EULER %s 0 0 '
        'FRAC 0 0 0 BFAC 0\\n" '
        '"$placement" >> "$outdir/PHASER.sol"\n'
        "    done\n"
        '    combined_sha="$(sha256sum "$outdir/PHASER.1.pdb" '
        "| awk '{print $1}')\"\n"
        '    output_mtz_sha="$(sha256sum "$outdir/PHASER.1.mtz" '
        "| awk '{print $1}')\"\n"
        '    printf \'{"execution_status":"completed_hit",'
        '"search_id":"%s","tool_version":"%s",'
        '"parent_copy_count":%s,"requested_partner_copy_count":%s,'
        '"partner_placement_count":%s,'
        '"selection_plan_id":"%s","partner_candidate_id":"%s",'
        '"partner_sequence_group_id":"%s",'
        '"incremental_llg":150.0,"partner_tfz":12.0,'
        '"score_cohort":"primary","top_solution_packed":true,'
        '"partner_placement_observed":true,'
        '"combined_coordinate_path":"PHASER.1.pdb",'
        '"combined_coordinate_sha256":"%s","output_mtz_path":"PHASER.1.mtz",'
        '"output_mtz_sha256":"%s"}\\n\' '
        '"$search_id" "$phaser_version" "$parent_copies" '
        '"$partner_copies" "$partner_copies" '
        '"$plan_id" "$candidate_id" "$partner_seq" "$combined_sha" '
        '"$output_mtz_sha" > "$outdir/partner_search_result.json"\n'
        "  fi\n"
        '  cp "$outdir/partner_search_result.json" '
        '"$outdir/partner_search_result.jsonl"\n'
        "  printf '{}\\n' > \"$outdir/phaser_command.json\"\n"
        '  printf "phaser {}\\n" > "$outdir/partner_search.eff"\n'
        '  if [[ "$outdir" != */p6/wrong-partner || '
        '"${FAKE_P6_WRONG_OMIT_NATIVE_LOG:-0}" != 1 ]]; then\n'
        '    printf "fake partner log\\n" > "$outdir/PHASER.log"\n'
        "  fi\n"
        '  printf "fake partner capture\\n" > "$outdir/phenix.phaser.capture.log"\n'
        'elif [[ "$mode" == placement_collect ]]; then\n'
        '  [[ -n "$outdir" && -n "$crystal_id" && -n "$search_id" && '
        '-n "$phaser_version" ]] || exit 20\n'
        "  copies=1\n"
        '  [[ "$outdir" != */multicopy/* ]] || copies=2\n'
        '  printf "fake grouped A coordinates\\n" > "$outdir/component_A.pdb"\n'
        '  printf "fake grouped B coordinates\\n" > "$outdir/component_B.pdb"\n'
        '  printf \'{"schema_version":"2.0",'
        '"inventory_id":"phaserplacements_%s",'
        '"adapter_version":"phaser-component-coordinate-inventory-v2",'
        '"crystal_id":"%s","search_id":"%s","phaser_version":"%s",'
        '"ordinal_mapping_status":"verified_exact_sol_to_model_bound_chains",'
        '"recombination_status":"verified_exact_combined_atom_partition",'
        '"can_create_fixed_component_evidence":true,'
        '"combined_atom_count":%s,"recombined_atom_count":%s,'
        '"placements":[\' '
        '"$(printf \'a%.0s\' {1..64})" "$crystal_id" "$search_id" '
        '"$phaser_version" "$((2 * copies))" "$((2 * copies))" '
        '> "$outdir/phaser_per_placement_inventory.json"\n'
        "  placement=0\n"
        "  for component in A B; do\n"
        "    component_placements=$copies\n"
        '    [[ "$component" != A ]] || component_placements=1\n'
        "    for ((i=1; i<=component_placements; i++)); do\n"
        "      placement=$((placement + 1))\n"
        "      [[ \"$placement\" -eq 1 ]] || printf ',' "
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        "      ensemble=fixed_parent\n"
        '      [[ "$component" == A ]] || ensemble=search_partner\n'
        '      printf \'{"placement_ordinal":%s,"component_label":"%s",'
        '"ensemble_id":"%s"}\' "$placement" "$component" "$ensemble" '
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        "    done\n"
        "  done\n"
        "  printf '],\"component_groups\":[' "
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        '  printf \'{"component_label":"A","ensemble_id":"fixed_parent",'
        '"expected_copy_count":%s,"observed_copy_count":%s,'
        '"placement_ordinals":[1]}\' "$copies" "$copies" '
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        '  printf \',{ "component_label":"B","ensemble_id":"search_partner",'
        '"expected_copy_count":%s,"observed_copy_count":%s,'
        '"placement_ordinals":[\' "$copies" "$copies" '
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        "  for ((i=1; i<=copies; i++)); do\n"
        "    [[ \"$i\" -eq 1 ]] || printf ',' "
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        "    printf '%s' \"$((1 + i))\" "
        '>> "$outdir/phaser_per_placement_inventory.json"\n'
        "  done\n"
        "  printf ']}] }\\n' >> \"$outdir/phaser_per_placement_inventory.json\"\n"
        'elif [[ "$mode" == partner_summary ]]; then\n'
        '  [[ -n "$refreshed" ]] || exit 19\n'
        '  mkdir -p "$(dirname "$refreshed")"\n'
        '  if [[ "$refreshed" == */p6/missing-partner-summary.json ]]; then\n'
        '    plan_sha="$(sha256sum "$partner_plan" | awk \'{print $1}\')"\n'
        "    plan_id=\"partnerplan_$(printf '9%.0s' {1..64})\"\n"
        '    printf \'{"plan_id":"%s","plan_sha256":"%s",'
        '"all_selected_attempts_retained":true,'
        '"candidate_count":1845,"selected_attempt_count":0,"result_count":0,'
        '"completed_hit_count":0,"deferred_cap_count":0,'
        '"unsearchable_candidate_count":1845}\\n\' '
        '"$plan_id" "$plan_sha" > "$refreshed"\n'
        "  else\n"
        '  printf \'{"all_selected_attempts_retained":true,'
        '"candidate_count":1845,"selected_attempt_count":1,"result_count":1,'
        '"completed_hit_count":1,"unsearchable_candidate_count":1844}\\n\' '
        '> "$refreshed"\n'
        "  fi\n"
        "else\n"
        "  exit 9\n"
        "fi\n"
        "FAKE_GTD\n"
        '      chmod 0755 "$env_bin/genome-to-diffraction"\n'
        f'      ln -sf {shlex.quote(sys.executable)} "$env_bin/python"\n'
        f'      ln -sf {shlex.quote(sha256sum)} "$env_bin/sha256sum"\n'
        "      for tool in nextflow mmseqs foldseek; do\n"
        "        printf '#!/usr/bin/env bash\\nexit 0\\n' > \"$env_bin/$tool\"\n"
        "      done\n"
        "      printf '#!/usr/bin/env bash\\nexit 0\\n' > "
        '"$env_root/lib/jvm/bin/java"\n'
        '      chmod 0755 "$env_bin/nextflow" "$env_bin/mmseqs" '
        '"$env_bin/foldseek" "$env_root/lib/jvm/bin/java"\n'
        "    fi\n"
        "    ;;\n"
        "  run)\n"
        '    [[ "${FAKE_PIXI_RUN_FAIL:-0}" != 1 ]] || exit 5\n'
        '    if [[ "${FAKE_PIXI_READONLY_TMP:-0}" == 1 ]]; then\n'
        '      mkdir -p "$TMPDIR/readonly/nested"\n'
        '      touch "$TMPDIR/readonly/nested/fixture"\n'
        '      chmod -R a-w "$TMPDIR/readonly"\n'
        "    fi\n"
        '    if [[ "${FAKE_PIXI_TERM_PARENT:-0}" == 1 ]]; then\n'
        '      kill -TERM "$PPID"\n'
        "      sleep 0.1\n"
        "    fi\n"
        "    ;;\n"
        "esac\n"
        "exit 0\n",
    )
    _write_executable(
        fake_bin / "sbatch",
        "#!/usr/bin/env bash\n"
        '[[ "${FAKE_SBATCH_REJECT:-0}" != 1 ]] || exit 1\n'
        f'printf "%s\\n" "$@" > '
        f"{shlex.quote(str(tmp_path / 'sbatch-args'))}\n"
        "echo 123\n",
    )
    _write_executable(
        fake_bin / "squeue",
        "#!/usr/bin/env bash\n"
        '[[ "${FAKE_SQUEUE_FAIL:-0}" != 1 ]] || exit 1\n'
        '[[ -z "${FAKE_SQUEUE_STATE:-}" ]] || echo "$FAKE_SQUEUE_STATE"\n',
    )
    _write_executable(fake_bin / "flock", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        fake_bin / "sacct",
        "#!/usr/bin/env bash\n"
        '[[ "${FAKE_SACCT_FAIL:-0}" != 1 ]] || exit 1\n'
        'echo "${FAKE_SACCT_STATE:-COMPLETED}|${FAKE_SACCT_EXIT:-0}:0"\n',
    )
    _write_executable(
        fake_bin / "scancel",
        f'#!/usr/bin/env bash\necho "$1" > {tmp_path / "cancelled-job"}\n',
    )
    (tooling / "pixi.path").write_text(f"{pixi}\n", encoding="utf-8")

    source, commit = _prepare_git_repositories(tmp_path)
    mirror = mirror_parent / "nf-genome_to_diffraction.git"
    _run(["git", "clone", "-q", "--mirror", str(source), str(mirror)], cwd=tmp_path)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["GIT_ALLOW_PROTOCOL"] = "file"
    environment["HOME"] = str(tmp_path)
    return dispatcher, smoke_job, environment, commit


def _select_fake_dispatcher_site(dispatcher: Path, site_id: str) -> None:
    """Select a fake site without creating production-shaped absolute paths."""

    if site_id == "marmic":
        return
    assert site_id == "viper-cpu"
    text = dispatcher.read_text(encoding="utf-8")
    marker = 'SITE_ID=marmic\nif [[ -e "$SITE_CONFIG" || -L "$SITE_CONFIG" ]]; then'
    replacement = (
        'SITE_ID=viper-cpu\nif [[ -e "$SITE_CONFIG" || -L "$SITE_CONFIG" ]]; then'
    )
    assert marker in text
    dispatcher.write_text(text.replace(marker, replacement, 1), encoding="utf-8")


def test_remote_dispatcher_full_fake_scheduler_lifecycle(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    source_bootstrap = tmp_path / "source-origin" / "bootstrap"
    dispatcher_digest = hashlib.sha256(
        (source_bootstrap / dispatcher.name).read_bytes()
    ).hexdigest()
    smoke_job_digest = hashlib.sha256(
        (source_bootstrap / smoke_job.name).read_bytes()
    ).hexdigest()
    smoke_job.write_text(
        smoke_job.read_text(encoding="utf-8") + "# stale installed copy\n",
        encoding="utf-8",
    )

    deployed = _run(
        [
            str(dispatcher),
            "deploy-tools",
            commit,
            dispatcher_digest,
            smoke_job_digest,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    deployed_fields = _decode_protocol(deployed.stdout)
    assert deployed_fields["deployed"] == "true"
    assert deployed_fields["commit"] == commit
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == dispatcher_digest
    assert hashlib.sha256(smoke_job.read_bytes()).hexdigest() == smoke_job_digest
    deployment_record = json.loads(
        (dispatcher.parent / "deployed-tools.json").read_text(encoding="utf-8")
    )
    assert deployment_record["dispatcher_sha256"] == dispatcher_digest
    assert deployment_record["smoke_job_sha256"] == smoke_job_digest

    lock_checksum = subprocess.run(
        ["sha256sum", tmp_path / "source-origin" / "pixi.lock"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[0]

    staged = _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(staged.stdout)["phase"] == "staged"

    submitted = _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(submitted.stdout)["job_id"] == "123"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    remote_root = smoke_job.parent.parent
    assert submitted_arguments[-4:] == [
        str(smoke_job),
        RUN_ID,
        str(remote_root),
        "smoke",
    ]

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment["FAKE_PIXI_READONLY_TMP"] = "1"
    spool_directory = tmp_path / "slurm-spool"
    spool_directory.mkdir()
    spooled_job = spool_directory / "slurm_script"
    shutil.copy2(smoke_job, spooled_job)
    _run(
        [str(spooled_job), RUN_ID, str(remote_root), "smoke"],
        cwd=tmp_path,
        environment=job_environment,
    )
    scratch = job_environment["SLURM_TMPDIR"] + f"/nf-gtd-123-{RUN_ID}"
    assert not Path(scratch).exists()

    status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    status_fields = _decode_protocol(status.stdout)
    assert status_fields["site_id"] == "marmic"
    assert status_fields["scheduler_state"] == "COMPLETED"
    assert status_fields["failure_class"] == "success"
    assert status_fields["terminal"] == "true"

    cancelled_environment = dict(environment)
    cancelled_environment["FAKE_SACCT_STATE"] = "CANCELLED"
    cancelled_status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=cancelled_environment,
    )
    cancelled_fields = _decode_protocol(cancelled_status.stdout)
    assert cancelled_fields["site_id"] == "marmic"
    assert cancelled_fields["failure_class"] == "unknown_failure"
    assert cancelled_fields["terminal"] == "true"

    logs = _run(
        [str(dispatcher), "logs", RUN_ID, OWNER_ID, "200"],
        cwd=tmp_path,
        environment=environment,
    )
    log_fields = _decode_protocol(logs.stdout)
    assert log_fields["site_id"] == "marmic"
    assert (
        "smoke_status=success"
        in base64.b64decode(log_fields["content_base64"]).decode()
    )

    archive_path = tmp_path / "collected.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        assert "manifest.json" in archive.getnames()
        assert "state/job-result.json" in archive.getnames()

    _run(
        [str(dispatcher), "cancel", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert (tmp_path / "cancelled-job").read_text(encoding="utf-8").strip() == "123"

    rejected = _run(
        [str(dispatcher), "clean", RUN_ID, OWNER_ID, "wrong"],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["failure_class"] == "wrapper_failure"
    assert (tmp_path / "remote-root" / "runs" / RUN_ID).is_dir()

    _run(
        [str(dispatcher), "clean", RUN_ID, OWNER_ID, RUN_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert not (tmp_path / "remote-root" / "runs" / RUN_ID).exists()


def test_control_matrix_submit_reuses_measured_control_slice_resources(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    run = remote_root / "runs" / CONTROL_MATRIX_RUN_ID
    state = run / "state"
    state.mkdir(parents=True)
    (run / "logs").mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="utf-8")
    (state / "phase").write_text("staged\n", encoding="utf-8")
    (state / "profile").write_text("control-matrix\n", encoding="utf-8")

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", CONTROL_MATRIX_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    assert submitted["job_id"] == "123"
    assert submitted["site_id"] == "marmic"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    assert "--cpus-per-task=8" in submitted_arguments
    assert "--mem=32G" in submitted_arguments
    assert "--time=24:00:00" in submitted_arguments
    control_matrix_body = (
        smoke_job.read_text(encoding="utf-8")
        .split("run_control_matrix() {", maxsplit=1)[1]
        .split("run_m4_copy_nextflow() {", maxsplit=1)[0]
    )
    assert '[[ "${SLURM_CPUS_PER_TASK:-0}" == 8 ]]' in control_matrix_body
    assert '--threads "${SLURM_CPUS_PER_TASK:-8}"' in control_matrix_body


def test_m6_input_qualification_uses_small_fixed_resources(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    run = remote_root / "runs" / M6_INPUTS_RUN_ID
    state = run / "state"
    state.mkdir(parents=True)
    (run / "logs").mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="utf-8")
    (state / "phase").write_text("staged\n", encoding="utf-8")
    (state / "profile").write_text("m6-inputs\n", encoding="utf-8")

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", M6_INPUTS_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    assert submitted["job_id"] == "123"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    assert "--cpus-per-task=1" in submitted_arguments
    assert "--mem=4G" in submitted_arguments
    assert "--time=00:45:00" in submitted_arguments
    m6_body = (
        smoke_job.read_text(encoding="utf-8")
        .split("run_m6_inputs() {", maxsplit=1)[1]
        .split("run_m4_copy_nextflow() {", maxsplit=1)[0]
    )
    assert '[[ "${SLURM_CPUS_PER_TASK:-0}" == 1 ]]' in m6_body
    assert "benchmark verify-m6-runner" in m6_body


@pytest.mark.parametrize(
    ("site_id", "policy_name", "policy_id"),
    [
        ("marmic", "execution-nextflow-marmic-v1.yaml", "m6_nextflow_slurm_marmic_v1"),
        ("viper-cpu", "execution-nextflow-v1.yaml", "m6_nextflow_slurm_v1"),
    ],
)
def test_m6_scientific_submit_uses_approved_bounded_resources(
    tmp_path: Path, site_id: str, policy_name: str, policy_id: str
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    _select_fake_dispatcher_site(dispatcher, site_id)
    remote_root = smoke_job.parent.parent
    run = remote_root / "runs" / M6_OPERATIONAL_RUN_ID
    state = run / "state"
    state.mkdir(parents=True)
    (run / "logs").mkdir()
    policy_relative = f"benchmarks/m6/{policy_name}"
    policy = run / "source" / policy_relative
    policy.parent.mkdir(parents=True)
    shutil.copy2(REPOSITORY / policy_relative, policy)
    apptainer_cache = run / "cache" / "apptainer"
    apptainer_cache.mkdir(parents=True)
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="utf-8")
    (state / "phase").write_text("staged\n", encoding="utf-8")
    (state / "profile").write_text("m6-operational\n", encoding="utf-8")
    (state / "site-id").write_text(f"{site_id}\n", encoding="utf-8")
    (state / "nextflow-profile").write_text(f"{site_id}\n", encoding="utf-8")
    (state / "execution-policy-relative").write_text(
        f"{policy_relative}\n", encoding="utf-8"
    )
    (state / "execution-policy-id").write_text(f"{policy_id}\n", encoding="utf-8")
    (state / "execution-policy-sha256").write_text(
        f"{hashlib.sha256(policy.read_bytes()).hexdigest()}\n", encoding="utf-8"
    )
    (state / "apptainer-cache-dir").write_text(f"{apptainer_cache}\n", encoding="utf-8")

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", M6_OPERATIONAL_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    assert submitted["job_id"] == "123"
    assert submitted["site_id"] == site_id
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    assert "--cpus-per-task=2" in submitted_arguments
    assert "--mem=8G" in submitted_arguments
    assert "--time=24:00:00" in submitted_arguments
    job_text = smoke_job.read_text(encoding="utf-8")
    m6_command = job_text.split("run_m6_nextflow() {", maxsplit=1)[1].split(
        "run_m6_scientific() {", maxsplit=1
    )[0]
    m6_body = job_text.split("run_m6_scientific() {", maxsplit=1)[1].split(
        "run_m4_copy_nextflow() {", maxsplit=1
    )[0]
    assert "run_m6_nextflow first" in m6_body
    assert "run_m6_nextflow resume -resume" in m6_body
    assert "m6_validation.nf" in job_text
    assert "load_m6_smoke_site_contract || return 2" in m6_body
    assert '-profile "$M6_NEXTFLOW_PROFILE"' in m6_command
    assert '--execution_policy "$M6_EXECUTION_POLICY"' in m6_command
    assert '--apptainer_cache_dir "$M6_APPTAINER_CACHE"' in m6_command
    assert "-profile viper-cpu" not in m6_command
    assert 'if [[ "$M6_SITE_ID" == viper-cpu ]]' in m6_body
    assert "NF_HELPER_VIPER_COMPUTE_CONTROLLER=managed-slurm" in m6_body
    assert "unset NF_HELPER_VIPER_COMPUTE_CONTROLLER" in m6_body
    assert 'export NXF_APPTAINER_CACHEDIR="$M6_APPTAINER_CACHE"' in m6_body
    assert '--execution-policy "$M6_EXECUTION_POLICY"' in m6_body
    assert '"execution_policy": "$M6_EXECUTION_POLICY_ID"' in m6_body
    assert "m6-child-resource-evidence.json" in m6_body
    assert m6_body.count("benchmark collect-m6-child-outputs") == 2
    assert "m6-first-child-outputs.json" in m6_body
    assert "m6-resume-child-outputs.json" in m6_body
    assert "first_child_output_sha256" in m6_body
    assert "resume_child_output_sha256" in m6_body
    dispatcher_body = dispatcher.read_text(encoding="utf-8")
    assert "artifacts/qualification/m6-first-child-outputs.json" in dispatcher_body
    assert "artifacts/qualification/m6-resume-child-outputs.json" in dispatcher_body
    assert "benchmark run-m6-scientific" not in m6_body
    assert "tool_runtime_timeouts" in m6_body


@pytest.mark.parametrize("source_archive", [False, True])
def test_marmic_m6_scientific_stage_binds_frozen_phenix_and_policy(
    tmp_path: Path, source_archive: bool
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    site_config = dispatcher.parent / "site.paths"
    site_config.write_text("marmic\n", encoding="ascii")
    site_config.chmod(0o600)
    database_paths = _write_database_paths(remote_root)
    database_manifest = Path(database_paths.read_text().splitlines()[2])
    database_manifest.write_text('{"schema_version":"1.0"}\n', encoding="ascii")
    phenix_manifest = tmp_path / "approved-phenix.json"
    phenix_manifest.write_text('{"schema_version":"1.0"}\n', encoding="ascii")
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()

    object_bytes = b"bounded M6 object\n"
    object_sha256 = hashlib.sha256(object_bytes).hexdigest()
    manifest_bytes = json.dumps(
        {
            "schema_version": "1.0",
            "protocol_id": "m6_independent_prokaryote_homomer_v1",
            "case_count": 63,
            "object_count": 1,
            "cases": [{"case_id": f"M6C{index:03d}"} for index in range(1, 64)],
            "objects": {
                object_sha256: {
                    "sha256": object_sha256,
                    "size_bytes": len(object_bytes),
                }
            },
        },
        sort_keys=True,
    ).encode("ascii")
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:") as archive:
        for name, payload in (
            ("runner_manifest.json", manifest_bytes),
            (f"objects/{object_sha256}", object_bytes),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    archive_bytes = archive_buffer.getvalue()
    arguments = [
        M6_OPERATIONAL_RUN_ID,
        commit,
        _lock_checksum(tmp_path),
        OWNER_ID,
        hashlib.sha256(archive_bytes).hexdigest(),
        str(len(archive_bytes)),
        hashlib.sha256(manifest_bytes).hexdigest(),
        "63",
        "1",
        "operational",
    ]

    rejected = _run(
        [str(dispatcher), "m6-scientific-stage", *arguments],
        cwd=tmp_path,
        environment=environment,
        input_data=archive_bytes,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["message"] == (
        "Marmic M6 requires its fixed Phenix binding"
    )

    stage_arguments = [*arguments, str(phenix_manifest), phenix_sha256]
    stage_payload = archive_bytes
    source_digest = ""
    if source_archive:
        source = tmp_path / "source-origin"
        helper_commit = _git(source / "external/nf-helper", "rev-parse", "HEAD")
        source_buffer = io.BytesIO()
        with tarfile.open(fileobj=source_buffer, mode="w:") as source_tar:
            source_tar.add(source, arcname=".", recursive=True)
        source_bytes = source_buffer.getvalue()
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        stage_arguments.extend([source_digest, str(len(source_bytes)), helper_commit])
        stage_payload = source_bytes + archive_bytes
        mirror = remote_root / "_cache/git/nf-genome_to_diffraction.git"
        mirror.rename(tmp_path / "unavailable-mirror")

    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "m6-scientific-stage",
                *stage_arguments,
            ],
            cwd=tmp_path,
            environment=environment,
            input_data=stage_payload,
        ).stdout
    )

    state = remote_root / "runs" / M6_OPERATIONAL_RUN_ID / "state"
    assert staged["site_id"] == "marmic"
    assert (state / "site-id").read_text().strip() == "marmic"
    assert (state / "nextflow-profile").read_text().strip() == "marmic"
    assert (state / "execution-policy-id").read_text().strip() == (
        "m6_nextflow_slurm_marmic_v1"
    )
    assert (state / "phenix-manifest").read_text().strip() == str(phenix_manifest)
    assert (state / "phenix-manifest-sha256").read_text().strip() == phenix_sha256
    assert (state / "m6-runner-case-count").read_text().strip() == "63"
    assert (state / "phase").read_text().strip() == "staged"
    if source_archive:
        assert (state / "source-archive-sha256").read_text().strip() == source_digest
        assert not mirror.exists()


@pytest.mark.parametrize(
    ("site_id", "nextflow_profile", "policy_name", "policy_id"),
    [
        (
            "marmic",
            "marmic",
            "execution-nextflow-marmic-v1.yaml",
            "m6_nextflow_slurm_marmic_v1",
        ),
        (
            "viper-cpu",
            "viper-cpu",
            "execution-nextflow-v1.yaml",
            "m6_nextflow_slurm_v1",
        ),
    ],
)
def test_m6_nextflow_smoke_binds_site_profile_policy_and_slurm_boundaries(
    tmp_path: Path,
    site_id: str,
    nextflow_profile: str,
    policy_name: str,
    policy_id: str,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _select_fake_dispatcher_site(dispatcher, site_id)
    remote_root = smoke_job.parent.parent
    lock_checksum = hashlib.sha256(
        (tmp_path / "source-origin" / "pixi.lock").read_bytes()
    ).hexdigest()
    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                commit,
                lock_checksum,
                OWNER_ID,
                "1",
                "m6-nextflow-smoke",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    run = remote_root / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    policy_relative = f"benchmarks/m6/{policy_name}"
    policy = run / "source" / policy_relative
    assert staged["site_id"] == site_id
    assert (state / "site-id").read_text().strip() == site_id
    assert (state / "nextflow-profile").read_text().strip() == nextflow_profile
    assert (state / "execution-policy-relative").read_text().strip() == (
        policy_relative
    )
    assert (state / "execution-policy-id").read_text().strip() == policy_id
    assert (state / "execution-policy-sha256").read_text().strip() == (
        hashlib.sha256(policy.read_bytes()).hexdigest()
    )
    assert (state / "apptainer-cache-dir").read_text().strip() == str(
        run / "cache" / "apptainer"
    )
    assert (run / "cache" / "apptainer").is_dir()
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["m6_site_contract"] == {
        "nextflow_profile": nextflow_profile,
        "execution_policy": policy_relative,
        "execution_policy_id": policy_id,
        "execution_policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
        "apptainer_cache_scope": "run_owned",
    }

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    assert submitted["job_id"] == "123"
    assert submitted["site_id"] == site_id
    arguments = (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    assert "--cpus-per-task=2" in arguments
    assert "--mem=8G" in arguments
    assert "--time=24:00:00" in arguments
    job_text = smoke_job.read_text(encoding="utf-8")
    body = job_text.split("run_m6_nextflow_smoke() {", maxsplit=1)[1].split(
        "run_m6_nextflow() {", maxsplit=1
    )[0]
    smoke_functions = job_text.split("load_m6_smoke_site_contract() {", maxsplit=1)[
        1
    ].split("run_m6_nextflow() {", maxsplit=1)[0]
    dispatcher_text = dispatcher.read_text(encoding="utf-8")
    assert "-stub-run" in job_text
    assert 'if [[ "$M6_SITE_ID" == viper-cpu ]]' in body
    assert "export NF_HELPER_VIPER_COMPUTE_CONTROLLER=managed-slurm" in body
    assert "unset NF_HELPER_VIPER_COMPUTE_CONTROLLER" in body
    assert '-profile "$M6_NEXTFLOW_PROFILE"' in smoke_functions
    assert '--execution-policy "$M6_EXECUTION_POLICY"' in smoke_functions
    assert '--apptainer_cache_dir "$M6_APPTAINER_CACHE"' in smoke_functions
    assert 'export NXF_APPTAINER_CACHEDIR="$M6_APPTAINER_CACHE"' in body
    assert "/ptmp/ashima/apptainer-cache" not in body
    assert "m6-nextflow-smoke-resource-evidence.json" in body
    assert "m6-nextflow-smoke-contract-evidence.json" in body
    assert 'record.get("identity_decision")' in body
    assert 'record.get("edge_observations")' in body
    assert 'rm -f -- "$before" "$after"' not in body
    for relative_path in (
        "artifacts/qualification/m6-nextflow-smoke-contract-evidence.json",
        "artifacts/qualification/m6-smoke-before-resume.sha256",
        "artifacts/qualification/m6-smoke-after-resume.sha256",
    ):
        assert relative_path in dispatcher_text
    assert 'job["requested_cpus"] != 32' in body
    assert 'job["requested_memory_gb"] != 16.0' in body
    assert 'job["requested_time_hours"] != 24.0' in body
    assert 'M6_SMOKE_CACHE="$RUN/cache/m6-nextflow-smoke"' in body
    assert 'M6_SMOKE_EXECUTION="$RUN/execution/m6-nextflow-smoke"' in body
    assert "m6-nextflow-smoke-cache-evidence.json" in body
    assert "operational_first_task_count" in body
    assert "operational_cached_resume_task_count" in body
    assert "leakage_cached_truthless_task_count" in body
    assert "leakage_completed_track_specific_task_count" in body
    assert "Stored process" not in body
    assert '"M6_SEARCH_PDB": 2' in body
    assert '"M6_SEARCH_FOLDSEEK": 2' in body
    assert '"M6_STAGE_COORDINATES": 1' in body
    assert 'controller_stages = record["controller_stages"]' in body
    assert "or len(jobs) != 25" in body
    assert "or len(controller_stages) != 1" in body
    assert 'len({job["native_job_id"] for job in search}) != 4' in body
    assert '"$stored" -eq 3' not in body
    assert "len(search) != 2" not in body
    assert '"acceptance_evidence": false' in body
    assert "cross_track_truthless_cache_reuse" in body

    contract_marker = (
        "\"$qualification/m6-nextflow-smoke-contract-evidence.json\" <<'PY'\n"
    )
    contract_script = body.split(contract_marker, maxsplit=1)[1].split(
        "\nPY\n", maxsplit=1
    )[0]
    fixture = REPOSITORY / "tests/fixtures/stubs/m6_nextflow/track_output"
    contract_output = tmp_path / "m6-nextflow-smoke-contract-evidence.json"
    _run(
        [
            sys.executable,
            "-",
            str(fixture / "m6_scientific_summary.json"),
            str(fixture / "m6_execution_verification.json"),
            str(fixture / "m6_case_results.jsonl"),
            str(contract_output),
        ],
        cwd=tmp_path,
        input_data=contract_script.encode(),
    )
    contract = json.loads(contract_output.read_text(encoding="utf-8"))
    assert contract["aggregate_contract"]["adapter_version"] == ("m6-nextflow-run-v2")
    assert [row["case_id"] for row in contract["case_contracts"]] == [
        "M6C001",
        "M6C057",
    ]
    assert all(
        row["identity_decision"]["adapter_version"] == "m6-identity-decision-v1"
        and isinstance(row["edge_observations"], list)
        for row in contract["case_contracts"]
    )


def test_m6_smoke_cache_evidence_requires_exact_cross_track_reuse(
    tmp_path: Path,
) -> None:
    job = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(encoding="utf-8")
    body = job.split("run_m6_nextflow_smoke() {", maxsplit=1)[1].split(
        "run_m6_nextflow() {", maxsplit=1
    )[0]
    marker = "\"$qualification/m6-nextflow-smoke-cache-evidence.json\" <<'PY'\n"
    validator = body.split(marker, maxsplit=1)[1].split("\nPY\n", maxsplit=1)[0]
    process_counts = {
        "M6_PLAN_TRACK": 1,
        "M6_IMPORT_CATALOGUE": 2,
        "M6_BUILD_SEARCH_BATCHES": 1,
        "M6_SEARCH_PDB": 2,
        "M6_SEARCH_FOLDSEEK": 2,
        "M6_PARTITION_DISCOVERY": 2,
        "M6_PREFLIGHT_CASE": 2,
        "M6_APPLY_POLICY": 1,
        "M6_STAGE_COORDINATES": 1,
        "M6_PREPARE_ACTIVE_CASE": 1,
        "M6_PREPARE_EARLY_CASE": 1,
        "M6_FIRST_COPY": 1,
        "M6_SELECT_SEEDS": 1,
        "M6_EMPTY_SEEDS": 1,
        "M6_ADDITIONAL_COPY": 1,
        "M6_SELECT_FINALISTS": 1,
        "M6_EMPTY_FINALISTS": 1,
        "M6_REFINEMENT": 1,
        "M6_ASSEMBLE_CASE": 1,
        "M6_ASSEMBLE_EMPTY_CASE": 1,
        "M6_AGGREGATE_TRACK": 1,
    }
    truthless = {
        "M6_IMPORT_CATALOGUE",
        "M6_SEARCH_PDB",
        "M6_SEARCH_FOLDSEEK",
    }

    def trace(path: Path, *, mode: str, extra_cached: str | None = None) -> None:
        lines = ["process\tstatus\ttag"]
        for process, count in process_counts.items():
            for index in range(count):
                status = mode
                if mode == "LEAKAGE":
                    status = (
                        "CACHED"
                        if process in truthless or process == extra_cached
                        else "COMPLETED"
                    )
                lines.append(
                    f"M6_VALIDATION_WORKFLOW:{process}\t{status}\t{process}:{index}"
                )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    first = tmp_path / "first.tsv"
    operational_resume = tmp_path / "operational-resume.tsv"
    leakage_resume = tmp_path / "leakage-resume.tsv"
    evidence_path = tmp_path / "cache-evidence.json"
    trace(first, mode="COMPLETED")
    trace(operational_resume, mode="CACHED")
    trace(leakage_resume, mode="LEAKAGE")

    accepted = _run(
        [
            sys.executable,
            "-",
            str(first),
            str(operational_resume),
            str(leakage_resume),
            str(evidence_path),
        ],
        cwd=tmp_path,
        input_data=validator.encode(),
    )
    assert accepted.stdout.strip() == b"26 26 6 20"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["cache_mechanism"] == "nextflow_resume"
    assert evidence["leakage_cached_truthless_task_count"] == 6
    assert evidence["leakage_completed_track_specific_task_count"] == 20
    assert evidence["coordinate_stage_process_count"] == 1

    trace(leakage_resume, mode="LEAKAGE", extra_cached="M6_STAGE_COORDINATES")
    rejected = _run(
        [
            sys.executable,
            "-",
            str(first),
            str(operational_resume),
            str(leakage_resume),
            str(evidence_path),
        ],
        cwd=tmp_path,
        input_data=validator.encode(),
        success=False,
    )
    assert b"exactly six truthless tasks" in rejected.stderr


def test_m6_nextflow_smoke_submit_rejects_changed_site_policy_state(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    lock_checksum = hashlib.sha256(
        (tmp_path / "source-origin" / "pixi.lock").read_bytes()
    ).hexdigest()
    _run(
        [
            str(dispatcher),
            "stage",
            M6_NEXTFLOW_SMOKE_RUN_ID,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "m6-nextflow-smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    state = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID / "state"
    (state / "nextflow-profile").write_text("viper-cpu\n", encoding="ascii")

    rejected = _run(
        [str(dispatcher), "submit", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )

    fields = _decode_protocol(rejected.stdout)
    assert fields["failure_class"] == "wrapper_failure"
    assert fields["message"] == "M6 run site policy mapping changed after staging"
    assert not (tmp_path / "sbatch-args").exists()


def test_dispatcher_rejects_an_unknown_site_configuration(tmp_path: Path) -> None:
    dispatcher, _, environment, _ = _prepare_remote_layout(tmp_path)
    site_config = dispatcher.parent / "site.paths"
    site_config.write_text("caller-selected-site\n", encoding="ascii")
    site_config.chmod(0o600)

    rejected = _run(
        [str(dispatcher), "readiness", "p0"],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )

    assert rejected.stdout == b""
    assert rejected.stderr == b"unsupported HPC site configuration\n"


def test_m6_nextflow_smoke_collects_v2_and_resume_evidence(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    run = remote_root / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    state.mkdir(parents=True)
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="utf-8")
    required = {
        "artifacts/qualification/m6-nextflow-smoke-contract-evidence.json",
        "artifacts/qualification/m6-nextflow-smoke-cache-evidence.json",
        "artifacts/qualification/m6-smoke-before-resume.sha256",
        "artifacts/qualification/m6-smoke-after-resume.sha256",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_scientific_summary.json",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_execution_verification.json",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/m6_case_results.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_candidate_rankings.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_model_policy_results.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_first_copy_results.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_additional_copy_results.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_refinement_results.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_sequence_results.jsonl",
        "artifacts/m6-nextflow-smoke/operational/m6_scientific/"
        "m6_sequence_summary.jsonl",
    }
    for relative_path in required:
        path = run / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    unlisted = run / "artifacts/m6-nextflow-smoke/operational/private.txt"
    unlisted.parent.mkdir(parents=True, exist_ok=True)
    unlisted.write_text("not collected\n", encoding="utf-8")

    archive = _run(
        [str(dispatcher), "collect", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    assert required <= names
    assert "artifacts/m6-nextflow-smoke/operational/private.txt" not in names


def test_failed_nextflow_task_diagnostics_are_bounded_and_collected(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    logs = run / "logs"
    state.mkdir(parents=True)
    logs.mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (state / "profile").write_text("m6-nextflow-smoke\n", encoding="ascii")
    (state / "phase").write_text("completed\n", encoding="ascii")
    (state / "failure-class").write_text("test_failure\n", encoding="ascii")
    task = run / "cache/m6-nextflow-smoke/work/a7" / ("1" * 32)
    task.mkdir(parents=True)
    diagnostic_files = {
        ".command.sh": "#!/bin/bash\ncopy fixture\n",
        ".command.run": "generated runner\n",
        ".command.log": "permission denied while copying output\n",
        ".command.out": "",
        ".command.err": "",
        ".command.trace": "nextflow.trace/v2\n",
        ".exitcode": "0",
    }
    for name, content in diagnostic_files.items():
        (task / name).write_text(content, encoding="ascii")
    (task / "private.env").write_text("not collected\n", encoding="ascii")
    application = logs / "m6-nextflow-smoke.log"
    application.write_text(
        f"Nextflow task failed\nWork dir:\n  {task}\n",
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "logs",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                OWNER_ID,
                "20",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    content = base64.b64decode(result["content_base64"]).decode()
    assert result["diagnostic_log_path"] == str(task / ".command.log")
    assert "--- failed command log ---" in content
    assert "permission denied while copying output" in content
    assert len(content.splitlines()) <= 20

    archive = _run(
        [str(dispatcher), "collect", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    task_relative = task.relative_to(run).as_posix()
    expected = {f"{task_relative}/{name}" for name in diagnostic_files}
    assert expected <= names
    assert f"{task_relative}/private.env" not in names


def test_failed_nextflow_task_diagnostics_reject_an_escaped_path(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    logs = run / "logs"
    state.mkdir(parents=True)
    logs.mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (state / "profile").write_text("m6-nextflow-smoke\n", encoding="ascii")
    (state / "phase").write_text("completed\n", encoding="ascii")
    (state / "failure-class").write_text("test_failure\n", encoding="ascii")
    escaped = tmp_path / "outside/work/a7" / ("2" * 32)
    escaped.mkdir(parents=True)
    (escaped / ".command.log").write_text("must not be returned\n", encoding="ascii")
    application = logs / "m6-nextflow-smoke.log"
    application.write_text(
        f"Nextflow task failed\nWork dir:\n  {escaped}\n",
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "logs",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                OWNER_ID,
                "20",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    content = base64.b64decode(result["content_base64"]).decode()
    assert result["diagnostic_log_path"] == ""
    assert "must not be returned" not in content

    archive = _run(
        [str(dispatcher), "collect", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    assert not any(name.startswith("cache/") for name in names)


def test_failed_nextflow_task_diagnostics_reject_a_symlinked_cache(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    logs = run / "logs"
    state.mkdir(parents=True)
    logs.mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (state / "profile").write_text("m6-nextflow-smoke\n", encoding="ascii")
    (state / "phase").write_text("completed\n", encoding="ascii")
    (state / "failure-class").write_text("test_failure\n", encoding="ascii")
    outside_cache = tmp_path / "outside-cache"
    task = outside_cache / "m6-nextflow-smoke/work/a7" / ("3" * 32)
    task.mkdir(parents=True)
    (task / ".command.log").write_text("outside cache\n", encoding="ascii")
    (run / "cache").symlink_to(outside_cache, target_is_directory=True)
    application = logs / "m6-nextflow-smoke.log"
    application.write_text(
        f"Nextflow task failed\nWork dir:\n  {task}\n",
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "logs",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                OWNER_ID,
                "20",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert result["diagnostic_log_path"] == ""

    archive = _run(
        [str(dispatcher), "collect", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    assert not any(name.startswith("cache/") for name in names)


def test_nextflow_diagnostics_require_a_complete_terminal_failure_marker(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    logs = run / "logs"
    state.mkdir(parents=True)
    logs.mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (state / "profile").write_text("m6-nextflow-smoke\n", encoding="ascii")
    (state / "phase").write_text("submitted\n", encoding="ascii")
    (state / "failure-class").write_text("test_failure\n", encoding="ascii")
    task = run / "cache/m6-nextflow-smoke/work/a7" / ("4" * 32)
    task.mkdir(parents=True)
    (task / ".command.log").write_text("diagnostic\n", encoding="ascii")
    application = logs / "m6-nextflow-smoke.log"
    application.write_text(
        f"Nextflow task failed\nWork dir:\n  {task}\n",
        encoding="ascii",
    )

    active = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "logs",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                OWNER_ID,
                "20",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert active["diagnostic_log_path"] == ""

    (state / "phase").write_text("completed\n", encoding="ascii")
    application.write_text(
        f"First failure\nWork dir:\n  {task}\nLater task\nWork dir:\n",
        encoding="ascii",
    )
    truncated = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "logs",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                OWNER_ID,
                "20",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert truncated["diagnostic_log_path"] == ""


def test_nextflow_logs_are_byte_bounded_and_prefer_nonempty_error(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    logs = run / "logs"
    state.mkdir(parents=True)
    logs.mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (state / "profile").write_text("m6-nextflow-smoke\n", encoding="ascii")
    (state / "phase").write_text("completed\n", encoding="ascii")
    (state / "failure-class").write_text("test_failure\n", encoding="ascii")
    task = run / "cache/m6-nextflow-smoke/work/a7" / ("5" * 32)
    task.mkdir(parents=True)
    (task / ".command.log").write_text("", encoding="ascii")
    (task / ".command.err").write_text("useful error\n", encoding="ascii")
    application = logs / "m6-nextflow-smoke.log"
    application.write_text(
        ("x" * (2 * 1024 * 1024 + 4096)) + f"\nWork dir:\n  {task}\n",
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "logs",
                M6_NEXTFLOW_SMOKE_RUN_ID,
                OWNER_ID,
                "20",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    content = base64.b64decode(result["content_base64"])
    assert result["diagnostic_log_path"] == str(task / ".command.err")
    assert len(content) <= 2 * 1024 * 1024
    assert b"useful error" in content


def test_oversized_nextflow_diagnostic_does_not_block_core_collection(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / M6_NEXTFLOW_SMOKE_RUN_ID
    state = run / "state"
    logs = run / "logs"
    state.mkdir(parents=True)
    logs.mkdir()
    (state / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (state / "profile").write_text("m6-nextflow-smoke\n", encoding="ascii")
    (state / "phase").write_text("completed\n", encoding="ascii")
    (state / "failure-class").write_text("test_failure\n", encoding="ascii")
    task = run / "cache/m6-nextflow-smoke/work/a7" / ("6" * 32)
    task.mkdir(parents=True)
    (task / ".command.sh").write_text("small command\n", encoding="ascii")
    (task / ".command.log").write_bytes(b"z" * (2 * 1024 * 1024 + 1))
    application = logs / "m6-nextflow-smoke.log"
    application.write_text(
        f"Nextflow task failed\nWork dir:\n  {task}\n",
        encoding="ascii",
    )

    archive = _run(
        [str(dispatcher), "collect", M6_NEXTFLOW_SMOKE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
        omission = collected.extractfile("state/nextflow-diagnostic-omissions.tsv")
        assert omission is not None
        omission_text = omission.read().decode()
    task_relative = task.relative_to(run).as_posix()
    assert "logs/m6-nextflow-smoke.log" in names
    assert f"{task_relative}/.command.sh" in names
    assert f"{task_relative}/.command.log" not in names
    assert ".command.log\t2097153\tper_file_limit" in omission_text


def test_remote_dispatcher_stages_checksum_verified_source_archive(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    source = tmp_path / "source-origin"
    checkout = tmp_path / "archive-checkout"
    _run(
        ["git", "clone", "-q", "--no-hardlinks", str(source), str(checkout)],
        cwd=tmp_path,
    )
    _run(
        [
            "git",
            "-c",
            "protocol.file.allow=always",
            "-C",
            str(checkout),
            "submodule",
            "update",
            "--init",
            "--recursive",
        ],
        cwd=tmp_path,
    )
    helper_commit = _git(checkout / "external/nf-helper", "rev-parse", "HEAD")
    source_archive = tmp_path / "source.tar"
    with tarfile.open(source_archive, mode="w") as archive:
        archive.add(checkout, arcname=".", recursive=True)
    archive_payload = source_archive.read_bytes()
    archive_digest = hashlib.sha256(archive_payload).hexdigest()
    lock_digest = hashlib.sha256((source / "pixi.lock").read_bytes()).hexdigest()

    staged = _run(
        [
            str(dispatcher),
            "stage-archive",
            SECOND_RUN_ID,
            commit,
            lock_digest,
            OWNER_ID,
            "1",
            "smoke",
            archive_digest,
            str(len(archive_payload)),
            helper_commit,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=archive_payload,
    )

    fields = _decode_protocol(staged.stdout)
    assert fields["phase"] == "staged"
    assert fields["commit"] == commit
    assert fields["nf_helper_commit"] == helper_commit
    run = tmp_path / "remote-root" / "runs" / SECOND_RUN_ID
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_archive_sha256"] == archive_digest
    assert (run / "state/source-archive-sha256").read_text().strip() == archive_digest
    assert (run / "source/.git").is_dir()
    assert (run / "source/external/nf-helper/.git").is_file()

    rejected = _run(
        [
            str(dispatcher),
            "stage-archive",
            "gtd-smoke-20260802T120002Z-0123456789ab-01234569",
            commit,
            lock_digest,
            OWNER_ID,
            "1",
            "smoke",
            "0" * 64,
            str(len(archive_payload)),
            helper_commit,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=archive_payload,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["failure_class"] == "transfer_failure"


def test_remote_dispatcher_rejects_command_injection_before_side_effects(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, _ = _prepare_remote_layout(tmp_path)
    result = _run(
        [str(dispatcher), "status", "../../bad;touch", OWNER_ID],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(result.stdout)["failure_class"] == "wrapper_failure"
    assert not (tmp_path / "bad").exists()

    original_dispatcher = hashlib.sha256(dispatcher.read_bytes()).hexdigest()
    rejected_deployment = _run(
        [str(dispatcher), "deploy-tools", "1" * 39 + ";", "0" * 64, "0" * 64],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(rejected_deployment.stdout)["failure_class"] == (
        "wrapper_failure"
    )
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == original_dispatcher


def test_remote_dispatcher_rejects_deployment_checksum_mismatch(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    original_dispatcher = hashlib.sha256(dispatcher.read_bytes()).hexdigest()
    original_smoke_job = hashlib.sha256(smoke_job.read_bytes()).hexdigest()

    rejected = _run(
        [str(dispatcher), "deploy-tools", commit, "0" * 64, "0" * 64],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )

    assert _decode_protocol(rejected.stdout)["failure_class"] == "transfer_failure"
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == original_dispatcher
    assert hashlib.sha256(smoke_job.read_bytes()).hexdigest() == original_smoke_job
    assert not (dispatcher.parent / "deployed-tools.json").exists()


def test_recovery_script_replaces_only_checksum_verified_tools(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    source_bootstrap = tmp_path / "source-origin" / "bootstrap"
    recovery = source_bootstrap / "nf-gtd-hpc-recover-tools"
    dispatcher_digest = hashlib.sha256(
        (source_bootstrap / dispatcher.name).read_bytes()
    ).hexdigest()
    job_digest = hashlib.sha256(
        (source_bootstrap / smoke_job.name).read_bytes()
    ).hexdigest()
    dispatcher.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
    dispatcher.chmod(0o755)

    recovered = _run(
        [
            str(recovery),
            str(dispatcher),
            commit,
            dispatcher_digest,
            job_digest,
            str((source_bootstrap / dispatcher.name).stat().st_size),
            str((source_bootstrap / smoke_job.name).stat().st_size),
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=(source_bootstrap / dispatcher.name).read_bytes()
        + (source_bootstrap / smoke_job.name).read_bytes(),
    )

    assert recovered.stdout == b"deployed\n"
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == dispatcher_digest
    assert hashlib.sha256(smoke_job.read_bytes()).hexdigest() == job_digest
    record = json.loads(
        (dispatcher.parent / "deployed-tools.json").read_text(encoding="utf-8")
    )
    assert record["commit"] == commit
    assert record["recovery_used"] is True

    rejected = _run(
        [
            str(recovery),
            str(dispatcher),
            commit,
            "0" * 64,
            job_digest,
            str((source_bootstrap / dispatcher.name).stat().st_size),
            str((source_bootstrap / smoke_job.name).stat().st_size),
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=(source_bootstrap / dispatcher.name).read_bytes()
        + (source_bootstrap / smoke_job.name).read_bytes(),
        success=False,
    )
    assert b"checksum differs from local review" in rejected.stderr
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == dispatcher_digest

    injected = _run(
        [
            str(recovery),
            f"{dispatcher};touch",
            commit,
            dispatcher_digest,
            job_digest,
            str((source_bootstrap / dispatcher.name).stat().st_size),
            str((source_bootstrap / smoke_job.name).stat().st_size),
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=(source_bootstrap / dispatcher.name).read_bytes()
        + (source_bootstrap / smoke_job.name).read_bytes(),
        success=False,
    )
    assert b"dispatcher path is invalid" in injected.stderr
    assert not (tmp_path / "touch").exists()


def test_recovery_script_rejects_legacy_pixi(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    source_bootstrap = tmp_path / "source-origin" / "bootstrap"
    recovery = source_bootstrap / "nf-gtd-hpc-recover-tools"
    dispatcher_source = source_bootstrap / dispatcher.name
    job_source = source_bootstrap / smoke_job.name
    dispatcher_digest = hashlib.sha256(dispatcher_source.read_bytes()).hexdigest()
    job_digest = hashlib.sha256(job_source.read_bytes()).hexdigest()
    legacy_environment = dict(environment)
    legacy_environment["FAKE_PIXI_VERSION"] = "0.74.0"

    rejected = _run(
        [
            str(recovery),
            str(dispatcher),
            commit,
            dispatcher_digest,
            job_digest,
            str(dispatcher_source.stat().st_size),
            str(job_source.stat().st_size),
        ],
        cwd=tmp_path,
        environment=legacy_environment,
        input_data=dispatcher_source.read_bytes() + job_source.read_bytes(),
        success=False,
    )

    assert b"Pixi 0.76.2 is required" in rejected.stderr
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == dispatcher_digest
    assert hashlib.sha256(smoke_job.read_bytes()).hexdigest() == job_digest


def test_recovery_script_bootstraps_an_absent_fixed_tool_directory(
    tmp_path: Path,
) -> None:
    _, _, environment, commit = _prepare_remote_layout(tmp_path)
    source_bootstrap = tmp_path / "source-origin" / "bootstrap"
    recovery = source_bootstrap / "nf-gtd-hpc-recover-tools"
    dispatcher_source = source_bootstrap / "nf-gtd-hpc-remote"
    job_source = source_bootstrap / "nf-gtd-hpc-smoke-job"
    anchor = tmp_path / "fresh-anchor"
    anchor.mkdir()
    root = anchor / "deleted-parent/fresh-remote-root"
    dispatcher = root / "_tooling/nf-gtd-hpc-remote"
    dispatcher_digest = hashlib.sha256(dispatcher_source.read_bytes()).hexdigest()
    job_digest = hashlib.sha256(job_source.read_bytes()).hexdigest()

    recovered = _run(
        [
            str(recovery),
            str(dispatcher),
            commit,
            dispatcher_digest,
            job_digest,
            str(dispatcher_source.stat().st_size),
            str(job_source.stat().st_size),
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=dispatcher_source.read_bytes() + job_source.read_bytes(),
    )

    assert recovered.stdout == b"deployed\n"
    assert hashlib.sha256(dispatcher.read_bytes()).hexdigest() == dispatcher_digest
    job = dispatcher.parent / "nf-gtd-hpc-smoke-job"
    assert hashlib.sha256(job.read_bytes()).hexdigest() == job_digest
    record = json.loads(
        (dispatcher.parent / "deployed-tools.json").read_text(encoding="utf-8")
    )
    pixi_path = dispatcher.parent / "pixi.path"
    assert pixi_path.is_file()
    assert stat.S_IMODE(pixi_path.stat().st_mode) == 0o600
    assert Path(pixi_path.read_text(encoding="utf-8").strip()).is_file()
    assert record["commit"] == commit
    assert record["recovery_used"] is True
    assert record["bootstrap_used"] is True
    assert record["root_bootstrap_used"] is True
    assert record["pixi_path_bootstrap_used"] is True
    assert record["pixi_executable"] == pixi_path.read_text(encoding="utf-8").strip()

    partial_root = tmp_path / "partial-remote-root"
    partial_tooling = partial_root / "_tooling"
    partial_tooling.mkdir(parents=True)
    partial_dispatcher = partial_tooling / "nf-gtd-hpc-remote"
    shutil.copy2(dispatcher_source, partial_dispatcher)
    rejected = _run(
        [
            str(recovery),
            str(partial_dispatcher),
            commit,
            dispatcher_digest,
            job_digest,
            str(dispatcher_source.stat().st_size),
            str(job_source.stat().st_size),
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=dispatcher_source.read_bytes() + job_source.read_bytes(),
        success=False,
    )
    assert b"fixed tool installation is partial" in rejected.stderr
    assert not (partial_tooling / "nf-gtd-hpc-smoke-job").exists()


def test_remote_tools_do_not_depend_on_dev_null(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    recovery = REPOSITORY / "bootstrap" / "nf-gtd-hpc-recover-tools"

    assert b"/dev/null" not in dispatcher.read_bytes()
    assert b"/dev/null" not in smoke_job.read_bytes()
    assert b"/dev/null" not in recovery.read_bytes()

    _run(
        [str(dispatcher), "readiness", "p2-control"],
        cwd=tmp_path,
        environment=environment,
    )
    discard = dispatcher.parent / ".discard"
    assert discard.is_file()
    assert stat.S_IMODE(discard.stat().st_mode) == 0o600


def _lock_checksum(tmp_path: Path) -> str:
    return subprocess.run(
        ["sha256sum", tmp_path / "source-origin" / "pixi.lock"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[0]


def _write_p0_paths(root: Path, *, unsafe: bool = False) -> Path:
    allowed = root / "p0-inputs"
    allowed.mkdir()
    manifests = allowed / "manifests"
    manifests.mkdir()
    mtz_inputs = allowed / "inputs"
    mtz_inputs.mkdir()
    (mtz_inputs / "CD6QS2P2G1_5.mtz").write_bytes(b"fixed CD6 test MTZ\n")
    database_root = allowed / "databases"
    database_root.mkdir()
    database_manifest = allowed / "database_manifest.json"
    database_manifest.write_text("{}\n", encoding="utf-8")
    inputs = []
    for name in ("catalogues.json", "crystals.json", "config.yaml", "phenix.json"):
        path = manifests / name
        path.write_text("{}\n", encoding="utf-8")
        inputs.append(path)
    p0_config = root / "_config" / "p0.paths"
    p0_config.parent.mkdir()
    crystal_path = str(inputs[1])
    if unsafe:
        crystal_path += ";touch-bad"
    p0_config.write_text(
        "\n".join(
            (
                str(allowed),
                str(inputs[0]),
                crystal_path,
                str(inputs[2]),
                str(database_root),
                str(database_manifest),
                str(inputs[3]),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    p0_config.chmod(0o600)
    return p0_config


def _write_database_paths(
    root: Path,
    *,
    storage_limit: str = "2000000000000",
    allowed_root: Path | None = None,
) -> Path:
    allowed = allowed_root if allowed_root is not None else root / "database-admin"
    database_root = allowed / "databases"
    manifests = allowed / "manifests"
    database_root.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(exist_ok=True)
    values = [
        str(allowed),
        str(database_root),
        str(manifests / "database_manifest-20260802.json"),
        storage_limit,
        "100000000000",
        "1800000000000",
        "200000000000",
    ]
    config = root / "_config" / "database.paths"
    config.parent.mkdir(exist_ok=True)
    config.write_text("\n".join(values) + "\n", encoding="utf-8")
    config.chmod(0o600)
    return config


def _p0_input_archive(
    source_id: str,
    database_manifest_sha256: str,
    phenix_manifest_sha256: str,
) -> bytes:
    bundle = {
        "database_manifest_sha256": database_manifest_sha256,
        "phenix_manifest_sha256": phenix_manifest_sha256,
        "schema_version": "1.0",
        "source_id": f"p0i_{source_id}",
    }
    files: dict[str, bytes] = {
        "bundle.json": (json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode(),
        "manifests/catalogues.json": b"{}\n",
        "manifests/crystals.json": b"{}\n",
        "manifests/config.yaml": b"schema_version: '1.0'\n",
        "inputs/proteome.faa": b">protein\nMA\n",
        "inputs/genome.fna": b">genome\nATGGCT\n",
        "inputs/annotation.gff": b"##gff-version 3\n",
        "inputs/annotation.gbff": b"LOCUS       TEST\n",
        "inputs/AD4QS1P4G2_18.mtz": b"MTZ AD4\n",
        "inputs/CD4QS2P2G1_15.mtz": b"MTZ CD4\n",
        "inputs/CD6QS2P2G1_5.mtz": b"MTZ CD6\n",
    }
    rows = ["sha256\tsize_bytes\tpath"]
    for name in sorted(files):
        payload = files[name]
        rows.append(f"{hashlib.sha256(payload).hexdigest()}\t{len(payload)}\t{name}")
    files["inventory.tsv"] = ("\n".join(rows) + "\n").encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name in sorted(files):
            payload = files[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mode = 0o444
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def _install_fake_database_runtime(run: Path, fake_bin: Path) -> None:
    bin_directory = run / "source" / ".pixi" / "envs" / "hpc" / "bin"
    bin_directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fake_bin / "stat", bin_directory / "stat")
    shutil.copy2(fake_bin / "flock", bin_directory / "flock")
    sha256sum = shutil.which("sha256sum")
    assert sha256sum is not None
    installed_sha256sum = bin_directory / "sha256sum"
    installed_sha256sum.unlink(missing_ok=True)
    _write_executable(
        installed_sha256sum,
        f'#!/usr/bin/env bash\nexec {shlex.quote(sha256sum)} "$@"\n',
    )
    _write_executable(bin_directory / "aria2c", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        bin_directory / "genome-to-diffraction",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "action=\n"
        "previous=\n"
        "report=\n"
        "manifest=\n"
        "full_verify=false\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_DATABASE_COMMAND_LOG"\n'
        'for argument in "$@"; do\n'
        '  [[ "$argument" != preflight ]] || action=preflight\n'
        '  [[ "$argument" != prepare ]] || action=prepare\n'
        '  [[ "$argument" != --full-verify ]] || full_verify=true\n'
        '  [[ "$previous" != --report ]] || report="$argument"\n'
        '  [[ "$previous" != --manifest ]] || manifest="$argument"\n'
        '  previous="$argument"\n'
        "done\n"
        'if [[ "$action" == preflight ]]; then\n'
        '  mkdir -p "$(dirname "$report")"\n'
        '  printf \'{"status":"passed","large_payload_started":false}\\n\' '
        '> "$report"\n'
        'elif [[ "$action" == prepare ]]; then\n'
        '  mkdir -p "$(dirname "$manifest")"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > "$manifest"\n'
        '  if [[ "$full_verify" == true ]]; then\n'
        '    printf \'{"verification_level":"full_checksums",'
        '"full_checksums":true}\\n\' > "${manifest%.json}.verification.json"\n'
        "  fi\n"
        "else\n"
        "  exit 9\n"
        "fi\n",
    )


def test_database_administration_uses_separate_fixed_start_boundary(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)

    missing = _run(
        [str(dispatcher), "database-readiness"],
        cwd=tmp_path,
        environment=environment,
    )
    missing_fields = _decode_protocol(missing.stdout)
    assert missing_fields["ready"] == "false"
    assert missing_fields["database_config_status"] == "absent_or_unsafe"
    assert list((remote_root / "runs").iterdir()) == []

    database_config = _write_database_paths(remote_root)
    ready = _run(
        [str(dispatcher), "database-readiness"],
        cwd=tmp_path,
        environment=environment,
    )
    ready_fields = _decode_protocol(ready.stdout)
    assert ready_fields["ready"] == "true", ready_fields
    assert ready_fields["database_config_status"] == "ready"
    assert (
        ready_fields["database_config_sha256"]
        == hashlib.sha256(database_config.read_bytes()).hexdigest()
    )
    assert not any(str(remote_root) in value for value in ready_fields.values())

    routine_stage = _run(
        [
            str(dispatcher),
            "stage",
            DATABASE_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "database",
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(routine_stage.stdout)["failure_class"] == "wrapper_failure"
    assert not (remote_root / "runs" / DATABASE_RUN_ID).exists()
    staged = _run(
        [
            str(dispatcher),
            "database-stage",
            DATABASE_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(staged.stdout)["profile"] == "database"
    run = remote_root / "runs" / DATABASE_RUN_ID
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["database_config_sha256"]
        == hashlib.sha256(database_config.read_bytes()).hexdigest()
    )
    assert (run / "state" / "hpc-environment-status").read_text().strip() == "ready"
    assert (run / "logs" / "pixi-install.log").is_file()
    source_bundle = run / "artifacts" / "database" / "source_bundle.json"
    source_bundle_sha256 = hashlib.sha256(source_bundle.read_bytes()).hexdigest()
    assert manifest["database_source_bundle_sha256"] == source_bundle_sha256
    assert (
        run / "state" / "database-source-bundle-sha256"
    ).read_text().strip() == source_bundle_sha256
    assert (run / "logs" / "database-source-stage.log").is_file()

    routine_submit = _run(
        [str(dispatcher), "submit", DATABASE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(routine_submit.stdout)["failure_class"] == (
        "wrapper_failure"
    )

    submitted = _run(
        [str(dispatcher), "database-submit", DATABASE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(submitted.stdout)["job_id"] == "123"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    assert "--partition=slurm" not in submitted_arguments
    assert "--cpus-per-task=4" in submitted_arguments
    assert "--mem=8G" in submitted_arguments
    assert "--time=24:00:00" in submitted_arguments
    assert submitted_arguments[-4:] == [
        str(smoke_job),
        DATABASE_RUN_ID,
        str(remote_root),
        "database",
    ]

    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    active_environment = dict(environment)
    active_environment["FAKE_SQUEUE_STATE"] = "RUNNING"
    concurrent = _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=active_environment,
    )
    assert _decode_protocol(concurrent.stdout)["scheduler_state"] == "SUBMITTED"

    host_sha256sum = Path(shutil.which("sha256sum") or "")
    assert host_sha256sum.is_file()
    host_sha256sum_sha256 = hashlib.sha256(host_sha256sum.read_bytes()).hexdigest()
    _install_fake_database_runtime(run, tmp_path / "fake-bin")
    assert hashlib.sha256(host_sha256sum.read_bytes()).hexdigest() == (
        host_sha256sum_sha256
    )
    assert not (run / "source/.pixi/envs/hpc/bin/sha256sum").is_symlink()
    scratch_parent = remote_root / "database-staging"
    scratch_parent.mkdir()
    command_log = tmp_path / "database-commands.log"
    job_environment = dict(environment)
    job_environment.update(
        {
            "SLURM_JOB_ID": "123",
            "SLURM_CPUS_PER_TASK": "4",
            "FAKE_STAT_DISTINCT": "0",
            "FAKE_DATABASE_COMMAND_LOG": str(command_log),
        }
    )
    spooled_job = tmp_path / "database-slurm-script"
    shutil.copy2(smoke_job, spooled_job)
    run_root_alias = tmp_path / "viper-ptmp-alias"
    run_root_alias.symlink_to(remote_root, target_is_directory=True)
    (run / "state" / "site-id").write_text("viper-cpu\n", encoding="ascii")
    _run(
        [str(spooled_job), DATABASE_RUN_ID, str(run_root_alias), "database"],
        cwd=tmp_path,
        environment=job_environment,
    )
    database_log = (run / "logs" / "database.log").read_text(encoding="utf-8")
    assert "scratch_parent_source=job_owned_ptmp" in database_log
    job_owned_parent = Path(
        scratch_parent / f"nf-gtd-database-parent-{os.getuid()}-123-{DATABASE_RUN_ID}"
    )
    assert not job_owned_parent.exists()

    result = json.loads((run / "state" / "job-result.json").read_text())
    assert result["failure_class"] == "success"
    assert result["profile"] == "database"
    configured_manifest = Path(database_config.read_text().splitlines()[2])
    assert configured_manifest.is_file()
    commands = command_log.read_text(encoding="utf-8")
    assert "databases preflight" in commands
    assert "databases prepare" in commands
    assert "--source-bundle" in commands
    assert "--full-verify" in commands
    assert "--threads 4" in commands
    assert str(job_owned_parent / f"nf-gtd-database-123-{DATABASE_RUN_ID}") in commands
    assert list(scratch_parent.iterdir()) == []

    archive_path = tmp_path / "database-collected.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", DATABASE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        names = archive.getnames()
    assert "logs/pixi-install.log" in names
    assert "logs/database-source-stage.log" in names
    assert "artifacts/database/source_bundle.json" in names
    assert "artifacts/database/preflight.json" in names
    assert "artifacts/database/database_manifest.full-verified.json" in names


def test_database_readiness_accepts_canonical_site_mount_alias(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    canonical_mount = tmp_path / "canonical-ptmp"
    canonical_mount.mkdir()
    mount_alias = tmp_path / "ptmp"
    mount_alias.symlink_to(canonical_mount, target_is_directory=True)
    database_config = _write_database_paths(
        remote_root,
        allowed_root=mount_alias / "ashima" / "nf-genome_to_diffraction",
    )

    ready = _run(
        [str(dispatcher), "database-readiness"],
        cwd=tmp_path,
        environment=environment,
    )

    fields = _decode_protocol(ready.stdout)
    assert fields["ready"] == "true", fields
    assert fields["database_config_status"] == "ready"
    assert (
        fields["database_config_sha256"]
        == hashlib.sha256(database_config.read_bytes()).hexdigest()
    )


def test_database_stage_fails_when_login_environment_install_fails(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    _write_database_paths(remote_root)
    failing_environment = dict(environment)
    failing_environment["FAKE_PIXI_INSTALL_FAIL"] = "1"

    failed = _run(
        [
            str(dispatcher),
            "database-stage",
            DATABASE_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
        ],
        cwd=tmp_path,
        environment=failing_environment,
        success=False,
    )

    fields = _decode_protocol(failed.stdout)
    assert fields["failure_class"] == "environment_failure"
    run = remote_root / "runs" / DATABASE_RUN_ID
    assert (run / "state" / "phase").read_text().strip() == "stage_failed"
    assert not (run / "state" / "job-id").exists()
    assert not (run / "state" / "hpc-environment-status").exists()
    assert (run / "logs" / "pixi-install.log").is_file()


def test_database_stage_classifies_login_source_transfer_failure(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_database_paths(remote_root)
    failing_environment = dict(environment)
    failing_environment["FAKE_DATABASE_SOURCE_FAIL"] = "1"

    failed = _run(
        [
            str(dispatcher),
            "database-stage",
            DATABASE_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
        ],
        cwd=tmp_path,
        environment=failing_environment,
        success=False,
    )

    fields = _decode_protocol(failed.stdout)
    assert fields["failure_class"] == "transfer_failure"
    run = remote_root / "runs" / DATABASE_RUN_ID
    assert (run / "state" / "phase").read_text().strip() == "stage_failed"
    assert (run / "state" / "failure-class").read_text().strip() == ("transfer_failure")
    assert (run / "logs" / "database-source-stage.log").is_file()
    assert not (run / "state" / "job-id").exists()


def test_database_login_stage_has_nonterminal_status_and_visible_logs(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    run = smoke_job.parent.parent / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("staging\n", encoding="ascii")
    source_log = run / "logs" / "database-source-stage.log"
    source_log.write_text("downloaded_bytes=1048576\n", encoding="ascii")

    status = _decode_protocol(
        _run(
            [str(dispatcher), "status", DATABASE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert status["phase"] == "staging"
    assert status["scheduler_state"] == "STAGING"
    assert status["terminal"] == "false"

    logs = _decode_protocol(
        _run(
            [str(dispatcher), "logs", DATABASE_RUN_ID, OWNER_ID, "20"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert logs["log_path"] == str(source_log)
    assert base64.b64decode(logs["content_base64"]).decode() == (
        "downloaded_bytes=1048576\n"
    )


def test_database_failure_log_is_included_without_accepting_a_path_argument(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_database_paths(remote_root)
    run = remote_root / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("completed\n", encoding="ascii")
    database_root = remote_root / "database-admin" / "databases"
    database_logs = database_root / "logs"
    database_logs.mkdir()
    diagnostic = database_logs / f"prostt5.download.{'a' * 32}.log"
    diagnostic.write_text("provider output\nexact failure\n", encoding="ascii")
    application = run / "logs" / "database.log"
    application.write_text(
        "preflight passed\n"
        f'{{"error": "database command failed; see {diagnostic}", '
        '"level": "error"}}\n',
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [str(dispatcher), "logs", DATABASE_RUN_ID, OWNER_ID, "8"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    content = base64.b64decode(result["content_base64"]).decode()
    assert result["log_path"] == str(application)
    assert result["diagnostic_log_path"] == str(diagnostic)
    assert "preflight passed" in content
    assert "--- failed database command log ---" in content
    assert "exact failure" in content
    assert len(content.splitlines()) <= 8


def test_database_failure_log_rejects_an_escaped_path(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_database_paths(remote_root)
    run = remote_root / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("completed\n", encoding="ascii")
    escaped = tmp_path / f"prostt5.download.{'b' * 32}.log"
    escaped.write_text("must not be returned\n", encoding="ascii")
    application = run / "logs" / "database.log"
    application.write_text(
        f'{{"error": "database command failed; see {escaped}", "level": "error"}}}}\n',
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [str(dispatcher), "logs", DATABASE_RUN_ID, OWNER_ID, "8"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    content = base64.b64decode(result["content_base64"]).decode()
    assert result["diagnostic_log_path"] == ""
    assert "must not be returned" not in content


def test_database_failed_staging_is_archived_without_deletion_or_path_input(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    config = _write_database_paths(remote_root)
    run = remote_root / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("completed\n", encoding="ascii")
    (run / "state" / "failure-class").write_text("software_failure\n", encoding="ascii")
    (run / "state" / "database-config-sha256").write_text(
        f"{hashlib.sha256(config.read_bytes()).hexdigest()}\n", encoding="ascii"
    )
    resource = remote_root / "database-admin" / "databases" / "resources" / "prostt5"
    failed = resource / f".staging-{'a' * 32}.failed"
    failed.mkdir(parents=True)
    (failed / "provider.log").write_text("preserved evidence\n", encoding="ascii")
    (failed / "provider-link.log").symlink_to("provider.log")
    (run / "logs" / "database.log").write_text(
        f'{{"level": "error", "staging_path": "{failed}"}}\n',
        encoding="ascii",
    )

    result = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "database-archive-failed",
                DATABASE_RUN_ID,
                OWNER_ID,
                DATABASE_RUN_ID,
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    destination = Path(result["destination"])
    assert result["archived"] == "true"
    assert result["file_count"] == "1"
    assert result["symlink_count"] == "1"
    assert result["total_bytes"] == str(len("preserved evidence\n"))
    assert not failed.exists()
    assert destination.is_dir()
    assert (destination / "provider.log").read_text() == "preserved evidence\n"
    assert (destination / "provider-link.log").is_symlink()
    record = json.loads(
        (run / "state" / "database-failed-staging-archive.json").read_text()
    )
    assert record["source"] == str(failed)
    assert record["destination"] == str(destination)
    assert record["symlink_count"] == 1
    assert "database_retained_staging_archived" in (run / "events.jsonl").read_text()
    archive_path = tmp_path / "archived-failure-evidence.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", DATABASE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        assert "state/database-failed-staging-archive.json" in archive.getnames()

    repeated = _run(
        [
            str(dispatcher),
            "database-archive-failed",
            DATABASE_RUN_ID,
            OWNER_ID,
            DATABASE_RUN_ID,
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(repeated.stdout)["failure_class"] == "filesystem_failure"
    assert destination.is_dir()


def test_database_failed_staging_archive_rejects_config_drift(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_database_paths(remote_root)
    run = remote_root / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("completed\n", encoding="ascii")
    (run / "state" / "failure-class").write_text("software_failure\n", encoding="ascii")
    (run / "state" / "database-config-sha256").write_text(
        f"{'0' * 64}\n", encoding="ascii"
    )
    failed = (
        remote_root
        / "database-admin"
        / "databases"
        / "resources"
        / "prostt5"
        / f".staging-{'b' * 32}.failed"
    )
    failed.mkdir(parents=True)
    (run / "logs" / "database.log").write_text(
        f'{{"level": "error", "staging_path": "{failed}"}}\n',
        encoding="ascii",
    )

    rejected = _run(
        [
            str(dispatcher),
            "database-archive-failed",
            DATABASE_RUN_ID,
            OWNER_ID,
            DATABASE_RUN_ID,
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )

    fields = _decode_protocol(rejected.stdout)
    assert fields["failure_class"] == "wrapper_failure"
    assert "configuration changed" in fields["message"]
    assert failed.is_dir()


def test_cancelled_database_staging_requires_terminal_scheduler_state(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    config = _write_database_paths(remote_root)
    run = remote_root / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("cancel_requested\n", encoding="ascii")
    (run / "state" / "job-id").write_text("123\n", encoding="ascii")
    (run / "state" / "database-config-sha256").write_text(
        f"{hashlib.sha256(config.read_bytes()).hexdigest()}\n", encoding="ascii"
    )
    staging = (
        remote_root
        / "database-admin"
        / "databases"
        / "resources"
        / "prostt5"
        / f".staging-{'d' * 32}"
    )
    staging.mkdir(parents=True)
    (staging / "partial.tar.gz").write_bytes(b"preserved partial\n")
    (run / "logs" / "database.log").write_text(
        json.dumps(
            {
                "message": "starting database command",
                "write_roots": [str(staging)],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )

    running_environment = dict(environment)
    running_environment["FAKE_SQUEUE_STATE"] = "RUNNING"
    active = _run(
        [
            str(dispatcher),
            "database-archive-failed",
            DATABASE_RUN_ID,
            OWNER_ID,
            DATABASE_RUN_ID,
        ],
        cwd=tmp_path,
        environment=running_environment,
        success=False,
    )
    assert _decode_protocol(active.stdout)["failure_class"] == "scheduler_rejection"
    assert staging.is_dir()

    cancelled_environment = dict(environment)
    cancelled_environment["FAKE_SACCT_STATE"] = "CANCELLED"
    (run / "logs" / "database.log").write_text(
        json.dumps(
            {
                "message": "starting database command",
                "write_roots": [str(staging), str(staging / "second")],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )
    multiple_roots = _run(
        [
            str(dispatcher),
            "database-archive-failed",
            DATABASE_RUN_ID,
            OWNER_ID,
            DATABASE_RUN_ID,
        ],
        cwd=tmp_path,
        environment=cancelled_environment,
        success=False,
    )
    assert _decode_protocol(multiple_roots.stdout)["message"] == (
        "cancelled command has multiple write roots"
    )
    (run / "logs" / "database.log").write_text(
        json.dumps(
            {
                "message": "starting database command",
                "write_roots": [str(staging)],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )
    archived = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "database-archive-failed",
                DATABASE_RUN_ID,
                OWNER_ID,
                DATABASE_RUN_ID,
            ],
            cwd=tmp_path,
            environment=cancelled_environment,
        ).stdout
    )
    destination = Path(archived["destination"])
    assert archived["archived"] == "true"
    assert archived["file_count"] == "1"
    assert not staging.exists()
    assert destination.is_dir()
    assert (destination / "partial.tar.gz").read_bytes() == b"preserved partial\n"


def test_database_failed_staging_archive_reports_absent_directory(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    config = _write_database_paths(remote_root)
    run = remote_root / "runs" / DATABASE_RUN_ID
    (run / "state").mkdir(parents=True)
    (run / "logs").mkdir()
    (run / "state" / "owner-id").write_text(f"{OWNER_ID}\n", encoding="ascii")
    (run / "state" / "profile").write_text("database\n", encoding="ascii")
    (run / "state" / "phase").write_text("completed\n", encoding="ascii")
    (run / "state" / "failure-class").write_text("software_failure\n", encoding="ascii")
    (run / "state" / "database-config-sha256").write_text(
        f"{hashlib.sha256(config.read_bytes()).hexdigest()}\n", encoding="ascii"
    )
    failed = (
        remote_root
        / "database-admin"
        / "databases"
        / "resources"
        / "prostt5"
        / f".staging-{'c' * 32}.failed"
    )
    failed.parent.mkdir(parents=True)
    (run / "logs" / "database.log").write_text(
        f'{{"level": "error", "staging_path": "{failed}"}}\n',
        encoding="ascii",
    )

    rejected = _run(
        [
            str(dispatcher),
            "database-archive-failed",
            DATABASE_RUN_ID,
            OWNER_ID,
            DATABASE_RUN_ID,
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )

    fields = _decode_protocol(rejected.stdout)
    assert fields["failure_class"] == "filesystem_failure"
    assert fields["message"] == (
        "failed-staging directory is absent or cannot be resolved"
    )

    failed.mkdir()
    (failed.parent / "outside.txt").write_text("outside\n", encoding="ascii")
    (failed / "link.txt").symlink_to("../outside.txt")
    symlink_rejected = _run(
        [
            str(dispatcher),
            "database-archive-failed",
            DATABASE_RUN_ID,
            OWNER_ID,
            DATABASE_RUN_ID,
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    symlink_fields = _decode_protocol(symlink_rejected.stdout)
    assert symlink_fields["failure_class"] == "filesystem_failure"
    assert symlink_fields["message"] == (
        "failed-staging symbolic link escapes its staging tree"
    )


@pytest.mark.parametrize(
    "storage_limit",
    ("02000000000000", "999999999999999999999999999999"),
)
def test_database_readiness_rejects_noncanonical_byte_counts(
    tmp_path: Path, storage_limit: str
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    _write_database_paths(smoke_job.parent.parent, storage_limit=storage_limit)

    result = _run(
        [str(dispatcher), "database-readiness"],
        cwd=tmp_path,
        environment=environment,
    )

    fields = _decode_protocol(result.stdout)
    assert fields["ready"] == "false"
    assert fields["database_config_status"] == "invalid_capacity"


def test_p0_readiness_is_sanitised_and_creates_no_run(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent

    missing = _run(
        [str(dispatcher), "readiness", "p0"],
        cwd=tmp_path,
        environment=environment,
    )
    missing_fields = _decode_protocol(missing.stdout)
    assert missing_fields == {
        "operation": "readiness",
        "profile": "p0",
        "ready": "false",
        "pixi_status": "ready",
        "pixi_version": "pixi 0.76.2",
        "p0_config_status": "absent_or_unsafe",
        "p0_config_sha256": "",
        "scope": "staging_prerequisites_only",
    }
    assert list((remote_root / "runs").iterdir()) == []

    p0_config = _write_p0_paths(remote_root)
    ready = _run(
        [str(dispatcher), "readiness", "p0"],
        cwd=tmp_path,
        environment=environment,
    )
    ready_fields = _decode_protocol(ready.stdout)
    assert ready_fields["ready"] == "true"
    assert ready_fields["p0_config_status"] == "ready"
    assert (
        ready_fields["p0_config_sha256"]
        == hashlib.sha256(p0_config.read_bytes()).hexdigest()
    )
    assert list((remote_root / "runs").iterdir()) == []

    p0_config.write_text(
        p0_config.read_text(encoding="utf-8").replace(
            "crystals.json", "crystals.json;touch-bad"
        ),
        encoding="utf-8",
    )
    unsafe = _run(
        [str(dispatcher), "readiness", "p0"],
        cwd=tmp_path,
        environment=environment,
    )
    unsafe_fields = _decode_protocol(unsafe.stdout)
    assert unsafe_fields["ready"] == "false"
    assert unsafe_fields["p0_config_status"] == "unsafe_path"
    assert not (tmp_path / "bad").exists()


def test_p0_configure_recreates_only_its_missing_fixed_parent(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    installed = _write_p0_paths(remote_root)
    payload = installed.read_bytes()
    checksum = hashlib.sha256(payload).hexdigest()
    local_candidate = tmp_path / "hpc-p0.paths"
    local_candidate.write_bytes(payload)
    installed.unlink()
    installed.parent.rmdir()

    configured = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "p0-configure",
                checksum,
                base64.b64encode(payload).decode("ascii"),
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    assert configured["configured"] == "true"
    assert installed.read_bytes() == local_candidate.read_bytes()
    assert stat.S_IMODE(installed.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(installed.stat().st_mode) == 0o600


def test_remote_dispatcher_rejects_legacy_pixi(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    legacy_environment = dict(environment)
    legacy_environment["FAKE_PIXI_VERSION"] = "0.74.0"

    readiness = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p0"],
            cwd=tmp_path,
            environment=legacy_environment,
        ).stdout
    )
    database_readiness = _decode_protocol(
        _run(
            [str(dispatcher), "database-readiness"],
            cwd=tmp_path,
            environment=legacy_environment,
        ).stdout
    )
    assert readiness["pixi_status"] == "version_mismatch"
    assert readiness["pixi_version"] == "pixi 0.74.0"
    assert readiness["ready"] == "false"
    assert database_readiness["pixi_status"] == "version_mismatch"
    assert database_readiness["ready"] == "false"

    lock_checksum = hashlib.sha256(
        (tmp_path / "source-origin" / "pixi.lock").read_bytes()
    ).hexdigest()
    rejected = _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=legacy_environment,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["failure_class"] == "environment_failure"
    assert not (remote_root / "runs" / RUN_ID).exists()


def test_p0_input_bundle_is_checksum_gated_immutable_and_configurable(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    login_home = tmp_path / "login-home"
    login_home.mkdir()
    environment["HOME"] = str(login_home)
    database_config = _write_database_paths(
        remote_root, allowed_root=tmp_path / "database-storage"
    )
    database_manifest = Path(
        database_config.read_text(encoding="ascii").splitlines()[2]
    )
    database_manifest.write_text('{"schema_version":"1.0"}\n', encoding="ascii")
    database_sha256 = hashlib.sha256(database_manifest.read_bytes()).hexdigest()
    phenix_directory = tmp_path / "Softwares" / "manifests"
    phenix_directory.mkdir(parents=True)
    phenix_manifest = phenix_directory / "phenix.json"
    phenix_manifest.write_text('{"schema_version":"1.0"}\n', encoding="ascii")
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    source_id = "4" * 64
    archive = _p0_input_archive(source_id, database_sha256, phenix_sha256)
    archive_sha256 = hashlib.sha256(archive).hexdigest()

    staged = _run(
        [
            str(dispatcher),
            "p0-inputs-stage",
            source_id,
            archive_sha256,
            str(len(archive)),
            database_sha256,
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=archive,
    )
    fields = _decode_protocol(staged.stdout)
    assert fields["p0_input_id"] == f"p0i_{source_id}"
    assert fields["archive_sha256"] == archive_sha256
    assert fields["scientific_input_count"] == "7"
    assert fields["regular_file_count"] == "17"
    destination = remote_root / "_p0_inputs" / f"p0i_{source_id}"
    assert (destination / "inputs/CD6QS2P2G1_5.mtz").read_bytes() == b"MTZ CD6\n"
    assert hashlib.sha256(
        (destination / "_archive.tar.gz").read_bytes()
    ).hexdigest() == (archive_sha256)
    assert destination.stat().st_mode & 0o777 == 0o555
    assert (destination / "bundle.json").stat().st_mode & 0o777 == 0o444

    candidate = base64.b64decode(fields["p0_paths_base64"])
    assert hashlib.sha256(candidate).hexdigest() == fields["p0_config_sha256"]
    candidate_lines = candidate.decode("ascii").splitlines()
    assert candidate_lines[0] == str(tmp_path)
    assert candidate_lines[4] == str(database_manifest.parent.parent / "databases")
    assert candidate_lines[5] == str(database_manifest)
    assert candidate_lines[6] == str(phenix_manifest)

    configured = _run(
        [
            str(dispatcher),
            "p0-configure",
            fields["p0_config_sha256"],
            base64.b64encode(candidate).decode("ascii"),
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(configured.stdout)["p0_config_status"] == "ready"
    readiness = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p0"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert readiness["ready"] == "true"

    repeated = _run(
        [
            str(dispatcher),
            "p0-inputs-stage",
            source_id,
            archive_sha256,
            str(len(archive)),
            database_sha256,
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=archive,
    )
    assert _decode_protocol(repeated.stdout)["p0_input_id"] == f"p0i_{source_id}"

    checksum_rejected = _run(
        [
            str(dispatcher),
            "p0-inputs-stage",
            "5" * 64,
            "0" * 64,
            str(len(archive)),
            database_sha256,
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=archive,
        success=False,
    )
    rejected_fields = _decode_protocol(checksum_rejected.stdout)
    assert rejected_fields["failure_class"] == "transfer_failure"
    assert not (remote_root / "_p0_inputs" / f"p0i_{'5' * 64}").exists()

    tampered_input = destination / "inputs/CD6QS2P2G1_5.mtz"
    tampered_input.chmod(0o644)
    tampered_input.write_bytes(b"changed\n")
    tamper_rejected = _run(
        [
            str(dispatcher),
            "p0-inputs-stage",
            source_id,
            archive_sha256,
            str(len(archive)),
            database_sha256,
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=archive,
        success=False,
    )
    tamper_fields = _decode_protocol(tamper_rejected.stdout)
    assert tamper_fields["failure_class"] == "transfer_failure"
    assert "checksum differs" in tamper_fields["message"]


def test_unknown_discovery_private_inputs_are_owned_and_submit_is_fixed(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    p0_config = _write_p0_paths(remote_root)
    p0_values = p0_config.read_text(encoding="ascii").splitlines()
    phenix_manifest = Path(p0_values[6])
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    lock_sha256 = hashlib.sha256(
        (tmp_path / "source-origin/pixi.lock").read_bytes()
    ).hexdigest()
    staged = _run(
        [
            str(dispatcher),
            "stage",
            UNKNOWN_DISCOVERY_RUN_ID,
            commit,
            lock_sha256,
            OWNER_ID,
            "1",
            "unknown-discovery",
            str(phenix_manifest),
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(staged.stdout)["profile"] == "unknown-discovery"

    local_root = tmp_path / "local-unknown-inputs"
    local_root.mkdir()
    review_root = local_root / "review"
    review_root.mkdir()
    fixture = materialise_unknown_pass1_public_fixture(review_root)
    afdb_map = local_root / "afdb_accession_map.tsv"
    afdb_map.write_text(
        "source_record_id\tuniprot_accession\n",
        encoding="ascii",
    )
    phase3_crystals = local_root / "phase3-crystals.json"
    atomic_write_json(
        phase3_crystals,
        {
            "schema_version": "1.0",
            "crystals": [
                {
                    "crystal_id": item.crystal_id,
                    "mtz": f"/approved/p0/inputs/{item.crystal_id}.mtz",
                    "catalogue_id": "public_catalogue",
                    "free_r_test_value": 0,
                    "allow_remote_sequence_submission": False,
                }
                for item in sorted(
                    fixture.crystals,
                    key=lambda value: value.crystal_id,
                )
            ],
        },
    )
    spec = local_root / UNKNOWN_DISCOVERY_SPEC_RELATIVE
    spec.parent.mkdir(parents=True)
    atomic_write_json(
        spec,
        {
            "schema_version": "1.0",
            "crystallographic_review_stage": str(fixture.review_stage),
            "execution_identity": str(fixture.execution_identity),
            "afdb_accession_map": str(afdb_map),
            "crystal_manifest": str(phase3_crystals),
        },
    )
    spec.chmod(0o600)
    bundle = build_unknown_discovery_input_bundle(
        repository=local_root,
        archive_path=local_root / "unknown-inputs.tar",
    )
    attached = _run(
        [
            str(dispatcher),
            "unknown-discovery-inputs-stage",
            UNKNOWN_DISCOVERY_RUN_ID,
            OWNER_ID,
            bundle.input_id,
            bundle.archive_sha256,
            str(bundle.archive_size_bytes),
            bundle.execution_identity_id,
            bundle.review_stage_index_id,
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=bundle.archive_path.read_bytes(),
    )
    attached_fields = _decode_protocol(attached.stdout)
    assert attached_fields["input_id"] == bundle.input_id
    run = remote_root / "runs" / UNKNOWN_DISCOVERY_RUN_ID
    inputs = run / "artifacts/unknown-discovery/inputs"
    assert inputs.is_dir() and not inputs.is_symlink()
    assert (inputs / "unknown_discovery_input_manifest.json").is_file()
    assert (inputs / "phase3_execution_identity.json").stat().st_mode & 0o777 == 0o444

    submitted = _run(
        [str(dispatcher), "submit", UNKNOWN_DISCOVERY_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(submitted.stdout)["profile"] == "unknown-discovery"
    sbatch = (tmp_path / "sbatch-args").read_text(encoding="utf-8")
    assert "--cpus-per-task=8" in sbatch
    assert "--mem=32G" in sbatch
    assert "--time=24:00:00" in sbatch

    parent_result = {
        "schema_version": "1.0",
        "run_id": UNKNOWN_DISCOVERY_RUN_ID,
        "profile": "unknown-discovery",
        "scheduler_state": "COMPLETED",
        "exit_code": 0,
        "failure_class": "success",
    }
    (run / "state/phase").write_text("completed\n", encoding="ascii")
    (run / "state/failure-class").write_text("success\n", encoding="ascii")
    (run / "state/exit-code").write_text("0\n", encoding="ascii")
    atomic_write_json(run / "state/job-result.json", parent_result)
    provider_package = (
        run / "artifacts/unknown-discovery/results/phase3_provider_discovery"
    )
    provider_package.mkdir(parents=True)
    atomic_write_json(
        provider_package / "phase3_provider_discovery_manifest.json",
        {
            "schema_version": "2.0",
            "package_id": "providerdiscovery_" + "d" * 64,
        },
    )
    child_staged = _run(
        [
            str(dispatcher),
            "stage",
            UNKNOWN_SCREEN_RUN_ID,
            commit,
            lock_sha256,
            "2" * 32,
            "2",
            "unknown-screen",
            str(phenix_manifest),
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(child_staged.stdout)["profile"] == "unknown-screen"
    screen_stage = _run(
        [
            str(dispatcher),
            "unknown-screen-stage",
            UNKNOWN_SCREEN_RUN_ID,
            "2" * 32,
            UNKNOWN_DISCOVERY_RUN_ID,
            OWNER_ID,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    screen_fields = _decode_protocol(screen_stage.stdout)
    assert screen_fields["parent_run_id"] == UNKNOWN_DISCOVERY_RUN_ID
    child = remote_root / "runs" / UNKNOWN_SCREEN_RUN_ID
    assert (child / "artifacts/unknown-screen/provider_preparation").is_dir()
    assert (child / "state/provider-preparation-sha256").is_file()
    child_submitted = _run(
        [str(dispatcher), "submit", UNKNOWN_SCREEN_RUN_ID, "2" * 32],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(child_submitted.stdout)["profile"] == "unknown-screen"
    child_sbatch = (tmp_path / "sbatch-args").read_text(encoding="utf-8")
    assert "--cpus-per-task=8" in child_sbatch
    assert "--mem=32G" in child_sbatch
    assert "--time=24:00:00" in child_sbatch
    fake_nextflow = child / "source/.pixi/envs/hpc/bin/nextflow"
    _write_executable(
        fake_nextflow,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "outdir=\n"
        "status=COMPLETED\n"
        "previous=\n"
        'for argument in "$@"; do\n'
        '  [[ "$previous" != --outdir ]] || outdir="$argument"\n'
        '  [[ "$argument" != -resume ]] || status=CACHED\n'
        '  previous="$argument"\n'
        "done\n"
        '[[ -n "$outdir" ]] || exit 2\n'
        'mkdir -p "$outdir/pipeline_info" '
        '"$outdir/phase3_offline_provider_input"\n'
        'printf \'{"schema_version":"2.0"}\\n\' > '
        '"$outdir/phase3_offline_provider_input/'
        'phase3_offline_provider_input.json"\n'
        'printf "process\\tstatus\\n" > "$outdir/pipeline_info/trace.tsv"\n'
        "for process in VALIDATE_PHASE3_OFFLINE_PROVIDER_INPUT "
        "VALIDATE_TASK05_INPUTS MTZ_PREFLIGHT ENUMERATE_MATTHEWS "
        "PREPARE_PREDICTED_MODELS PREPARE_EXPERIMENTAL_MODELS "
        "DISPATCH_CRYSTAL_ITEM RUN_PHASE3_FIRST_COPY_PHASER "
        "BUILD_PHASE3_MR_SEED_REVIEW; do\n"
        '  printf "%s\\t%s\\n" "$process" "$status" '
        '>> "$outdir/pipeline_info/trace.tsv"\n'
        "done\n"
        "for name in report.html timeline.html dag.html; do\n"
        '  printf "stub\\n" > "$outdir/pipeline_info/$name"\n'
        "done\n",
    )
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_CPUS_PER_TASK"] = "8"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "unknown-screen-slurm-tmp")
    _run(
        [str(smoke_job), UNKNOWN_SCREEN_RUN_ID, str(remote_root), "unknown-screen"],
        cwd=tmp_path,
        environment=job_environment,
    )
    screen_result = json.loads(
        (child / "state/job-result.json").read_text(encoding="utf-8")
    )
    assert screen_result["failure_class"] == "success"
    assert screen_result["scheduler_state"] == "COMPLETED"
    screen_trace = (
        child / "artifacts/qualification/unknown-screen-resume-pipeline-info/trace.tsv"
    ).read_text(encoding="utf-8")
    assert "RETRIEVE_AFDB_EXACT" not in screen_trace
    assert "REGISTER_PDB_COORDINATES" not in screen_trace
    assert screen_trace.count("CACHED") == 9

    decision = local_root / "a-seed.tsv"
    decision.write_text(
        "checkpoint\towned_parent_run_id\treview_package_id\t"
        "review_package_manifest_sha256\tcrystal_id\titem_id\tdecision\t"
        "reviewer\treviewed_at\treason\n"
        f"a_seed\t{UNKNOWN_SCREEN_RUN_ID}\treviewpkg_{'1' * 64}\t"
        f"{'2' * 64}\tcrystal_a\tsolution_1\tapprove\treviewer\t"
        "2026-08-25T00:00:00Z\tmap inspected\n",
        encoding="ascii",
    )
    single_spec = local_root / UNKNOWN_SINGLE_SPEC_RELATIVE
    atomic_write_json(
        single_spec,
        {
            "schema_version": "1.0",
            "decisions": [
                {
                    "crystal_id": "crystal_a",
                    "path": str(decision),
                    "sha256": hashlib.sha256(decision.read_bytes()).hexdigest(),
                }
            ],
        },
    )
    single_spec.chmod(0o600)
    single_bundle = build_unknown_single_component_input_bundle(
        repository=local_root,
        parent_run_id=UNKNOWN_SCREEN_RUN_ID,
        archive_path=local_root / "unknown-single-inputs.tar",
    )
    single_staged = _run(
        [
            str(dispatcher),
            "stage",
            UNKNOWN_SINGLE_RUN_ID,
            commit,
            lock_sha256,
            "3" * 32,
            "3",
            "unknown-single-component",
            str(phenix_manifest),
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(single_staged.stdout)["profile"] == (
        "unknown-single-component"
    )
    single = remote_root / "runs" / UNKNOWN_SINGLE_RUN_ID
    fake_python = single / "source/.pixi/envs/hpc/bin/python"
    fake_python.unlink()
    _write_executable(
        fake_python,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'case " $* " in\n'
        '  *" stage-handoff "*)\n'
        "    child=\n"
        "    previous=\n"
        '    for argument in "$@"; do\n'
        '      [[ "$previous" != --child-run-root ]] || child="$argument"\n'
        '      previous="$argument"\n'
        "    done\n"
        '    output="$child/artifacts/unknown-single-component"\n'
        '    mkdir -p "$output/owned_run_registry" '
        '"$output/a_seed_stages/crystal_a" "$output/hypotheses"\n'
        '    printf \'{"schema_version":"1.0"}\\n\' > '
        '"$output/owned_run_registry/phase3_owned_run_registry.json"\n'
        '    printf \'{"schema_version":"2.0"}\\n\' > '
        '"$output/owned_run_registry/phase3_execution_identity.json"\n'
        '    printf \'{"schema_version":"1.0","crystals":[]}\\n\' > '
        '"$output/reviewed_crystals.json"\n'
        '    printf \'{"schema_version":"1.0"}\\n\' > '
        '"$output/unknown_single_component_stage_manifest.json"\n'
        "    ;;\n"
        "esac\n",
    )
    single_attached = _run(
        [
            str(dispatcher),
            "unknown-single-component-stage",
            UNKNOWN_SINGLE_RUN_ID,
            "3" * 32,
            UNKNOWN_SCREEN_RUN_ID,
            "2" * 32,
            single_bundle.input_id,
            single_bundle.archive_sha256,
            str(single_bundle.archive_size_bytes),
        ],
        cwd=tmp_path,
        environment=environment,
        input_data=single_bundle.archive_path.read_bytes(),
    )
    single_fields = _decode_protocol(single_attached.stdout)
    assert single_fields["parent_run_id"] == UNKNOWN_SCREEN_RUN_ID
    assert (single / "state/unknown-single-stage-sha256").is_file()
    single_submitted = _run(
        [str(dispatcher), "submit", UNKNOWN_SINGLE_RUN_ID, "3" * 32],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(single_submitted.stdout)["profile"] == (
        "unknown-single-component"
    )
    single_nextflow = single / "source/.pixi/envs/hpc/bin/nextflow"
    _write_executable(
        single_nextflow,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "outdir=\n"
        "status=COMPLETED\n"
        "previous=\n"
        'for argument in "$@"; do\n'
        '  [[ "$previous" != --outdir ]] || outdir="$argument"\n'
        '  [[ "$argument" != -resume ]] || status=CACHED\n'
        '  previous="$argument"\n'
        "done\n"
        'mkdir -p "$outdir/pipeline_info"\n'
        'printf "process\\tstatus\\n" > "$outdir/pipeline_info/trace.tsv"\n'
        "for process in VALIDATE_TASK05_INPUTS MTZ_PREFLIGHT "
        "STAGE_PHASE3_APPROVED_MR_SEEDS RUN_BRIEF_REFINEMENT "
        "BUILD_LIVE_SEQUENCE_CHECKPOINT; do\n"
        '  printf "%s\\t%s\\n" "$process" "$status" '
        '>> "$outdir/pipeline_info/trace.tsv"\n'
        "done\n"
        "for name in report.html timeline.html dag.html; do\n"
        '  printf "stub\\n" > "$outdir/pipeline_info/$name"\n'
        "done\n",
    )
    single_job_environment = dict(environment)
    single_job_environment["SLURM_JOB_ID"] = "123"
    single_job_environment["SLURM_CPUS_PER_TASK"] = "8"
    single_job_environment["SLURM_TMPDIR"] = str(tmp_path / "unknown-single-slurm-tmp")
    _run(
        [
            str(smoke_job),
            UNKNOWN_SINGLE_RUN_ID,
            str(remote_root),
            "unknown-single-component",
        ],
        cwd=tmp_path,
        environment=single_job_environment,
    )
    single_result = json.loads(
        (single / "state/job-result.json").read_text(encoding="utf-8")
    )
    assert single_result["failure_class"] == "success"
    single_trace = (
        single
        / "artifacts/qualification"
        / "unknown-single-component-resume-pipeline-info/trace.tsv"
    ).read_text(encoding="utf-8")
    assert single_trace.count("CACHED") == 5
    assert "RUN_PHASE3_FIRST_COPY_PHASER" not in single_trace


def test_p0_configuration_is_create_only_checksum_gated_and_allows_owned_home(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, _ = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    p0_config = _write_p0_paths(remote_root)
    lines = p0_config.read_text(encoding="ascii").splitlines()
    lines[0] = str(remote_root)
    payload = ("\n".join(lines) + "\n").encode("ascii")
    checksum = hashlib.sha256(payload).hexdigest()
    p0_config.unlink()
    environment["HOME"] = str(remote_root)

    configured = _run(
        [
            str(dispatcher),
            "p0-configure",
            checksum,
            base64.b64encode(payload).decode("ascii"),
        ],
        cwd=tmp_path,
        environment=environment,
    )

    fields = _decode_protocol(configured.stdout)
    assert fields == {
        "operation": "p0-configure",
        "configured": "true",
        "p0_config_sha256": checksum,
        "p0_config_status": "ready",
    }
    assert p0_config.read_bytes() == payload
    assert p0_config.stat().st_mode & 0o777 == 0o600
    ready = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p0"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert ready["ready"] == "true"

    repeated = _run(
        [
            str(dispatcher),
            "p0-configure",
            checksum,
            base64.b64encode(payload).decode("ascii"),
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(repeated.stdout)["message"] == (
        "P0 configuration already exists"
    )


def test_p0_stage_fingerprints_fixed_config_and_rejects_post_stage_changes(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    p0_config = _write_p0_paths(remote_root)

    staged = _run(
        [
            str(dispatcher),
            "stage",
            P0_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p0",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    staged_fields = _decode_protocol(staged.stdout)
    assert staged_fields["profile"] == "p0"
    run = remote_root / "runs" / P0_RUN_ID
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["p0_config_sha256"]
        == hashlib.sha256(p0_config.read_bytes()).hexdigest()
    )
    database_manifest = Path(p0_config.read_text(encoding="utf-8").splitlines()[5])
    assert (
        manifest["database_manifest_sha256"]
        == hashlib.sha256(database_manifest.read_bytes()).hexdigest()
    )
    assert (run / "state" / "hpc-environment-status").read_text().strip() == "ready"
    assert (run / "logs" / "pixi-install.log").is_file()

    p0_config.write_text(
        p0_config.read_text(encoding="utf-8").replace(
            "crystals.json", "crystals.json;touch-bad"
        ),
        encoding="utf-8",
    )

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "321"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    failed = _run(
        [str(smoke_job), P0_RUN_ID, str(remote_root), "p0"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )
    assert failed.returncode != 0
    failure = (remote_root / "runs" / P0_RUN_ID / "state" / "failure-class").read_text(
        encoding="utf-8"
    )
    assert failure.strip() == "environment_failure"
    assert not (tmp_path / "bad").exists()


def test_p0_stage_fails_when_login_environment_install_fails(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    failing_environment = dict(environment)
    failing_environment["FAKE_PIXI_INSTALL_FAIL"] = "1"

    failed = _run(
        [
            str(dispatcher),
            "stage",
            P0_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p0",
        ],
        cwd=tmp_path,
        environment=failing_environment,
        success=False,
    )

    assert _decode_protocol(failed.stdout)["failure_class"] == "environment_failure"
    run = remote_root / "runs" / P0_RUN_ID
    assert (run / "state" / "phase").read_text().strip() == "stage_failed"
    assert not (run / "state" / "job-id").exists()
    assert not (run / "state" / "hpc-environment-status").exists()
    assert (run / "logs" / "pixi-install.log").is_file()


def _install_fake_p0_runtime(run: Path, *, all_cached: bool = True) -> None:
    bin_directory = run / "source" / ".pixi" / "envs" / "hpc" / "bin"
    bin_directory.mkdir(parents=True, exist_ok=True)
    _write_executable(
        bin_directory / "genome-to-diffraction",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ -n "${FAKE_P0_GTD_COMMAND_LOG:-}" ]]; then\n'
        '  printf \'%s\\n\' "$*" >> "$FAKE_P0_GTD_COMMAND_LOG"\n'
        "fi\n"
        "mode=\n"
        "previous=\n"
        "full_verify=false\n"
        'for argument in "$@"; do\n'
        '  [[ "$argument" != databases ]] || mode=databases\n'
        '  [[ "$argument" != --full-verify ]] || full_verify=true\n'
        '  if [[ "$previous" == --verification-log ]]; then\n'
        "    printf 'verified\\n' > \"$argument\"\n"
        '  elif [[ "$mode" == databases && "$previous" == --manifest ]]; then\n'
        "    printf '{}\\n' > \"$argument\"\n"
        '    printf \'{"schema_version":"1.0","verification_level":'
        '"inventory_metadata_and_functional_smoke","full_checksums":false}\\n\' > '
        '"${argument%.json}.verification.json"\n'
        "  fi\n"
        '  previous="$argument"\n'
        "done\n"
        '[[ "$mode" != databases || "$full_verify" == false ]]\n',
    )
    status = "CACHED" if all_cached else "COMPLETED"
    _write_executable(
        bin_directory / "nextflow",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "outdir=\n"
        "previous=\n"
        'for argument in "$@"; do\n'
        '  if [[ "$previous" == --outdir ]]; then outdir="$argument"; fi\n'
        '  previous="$argument"\n'
        "done\n"
        '[[ -n "$outdir" ]]\n'
        'mkdir -p "$outdir/pipeline_info" "$outdir/scope" '
        '"$outdir/catalogue" "$outdir/preflight" "$outdir/matthews"\n'
        "printf 'task_id\\tstatus\\n' > \"$outdir/pipeline_info/trace.tsv\"\n"
        f"for task in 1 2 3 4; do printf '%s\\t{status}\\n' \"$task\"; done "
        '>> "$outdir/pipeline_info/trace.tsv"\n'
        "for name in report.html timeline.html dag.html; do "
        "printf '<html></html>\\n' > \"$outdir/pipeline_info/$name\"; done\n"
        'printf \'{"status":"task05_preflight_complete_downstream_deferred"}\\n\' '
        '> "$outdir/scope/pipeline_scope.json"\n'
        "printf '{}\\n' > \"$outdir/catalogue/catalogue_import_manifest.json\"\n"
        "printf '{}\\n' > \"$outdir/preflight/mtz_preflight.jsonl\"\n"
        "printf 'header\\n' > \"$outdir/preflight/mtz_preflight.tsv\"\n"
        "printf '# preflight\\n' > \"$outdir/preflight/preflight_report.md\"\n"
        "printf '# matthews\\n' > \"$outdir/matthews/matthews_report.md\"\n",
    )


@pytest.mark.parametrize(
    ("all_cached", "success", "failure_class"),
    [(True, True, "success"), (False, False, "test_failure")],
)
def test_p0_job_enforces_the_cached_resume_gate(
    tmp_path: Path,
    all_cached: bool,
    success: bool,
    failure_class: str,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    _run(
        [
            str(dispatcher),
            "stage",
            P0_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p0",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    run = remote_root / "runs" / P0_RUN_ID
    _install_fake_p0_runtime(run, all_cached=all_cached)
    submitted = _run(
        [str(dispatcher), "submit", P0_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    assert _decode_protocol(submitted.stdout)["job_id"] == "123"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    assert "--time=24:00:00" in submitted_arguments
    command_log = tmp_path / "p0-gtd-commands.log"
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment["FAKE_PIXI_INSTALL_FAIL"] = "1"
    job_environment["FAKE_P0_GTD_COMMAND_LOG"] = str(command_log)

    _run(
        [str(smoke_job), P0_RUN_ID, str(remote_root), "p0"],
        cwd=tmp_path,
        environment=job_environment,
        success=success,
    )

    result = json.loads((run / "state" / "job-result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == failure_class
    p0_log = (run / "logs" / "p0.log").read_text(encoding="utf-8")
    assert "phase=pixi_environment_verify profile=p0" in p0_log
    assert "phase=pixi_install profile=p0" not in p0_log
    commands = command_log.read_text(encoding="utf-8")
    assert "phenix verify" in commands
    assert "--no-command-timeout" in commands
    assert "--command-timeout-seconds" not in commands
    if all_cached:
        resume = json.loads(
            (run / "artifacts" / "qualification" / "resume-check.json").read_text(
                encoding="utf-8"
            )
        )
        assert resume["cached_process_count"] == 4
        assert resume["all_deterministic_processes_cached"] is True
        archive_path = tmp_path / "p0-collected.tar.gz"
        archive_path.write_bytes(
            _run(
                [str(dispatcher), "collect", P0_RUN_ID, OWNER_ID],
                cwd=tmp_path,
                environment=environment,
            ).stdout
        )
        with tarfile.open(archive_path, "r:gz") as archive:
            assert (
                "artifacts/qualification/"
                "database_manifest.p0-revalidated.verification.json"
            ) in archive.getnames()
        bounded_verification = json.loads(
            (
                run
                / "artifacts"
                / "qualification"
                / "database_manifest.p0-revalidated.verification.json"
            ).read_text(encoding="utf-8")
        )
        assert bounded_verification["verification_level"] == (
            "inventory_metadata_and_functional_smoke"
        )
        assert bounded_verification["full_checksums"] is False


def _install_fake_p1_runtime(run: Path) -> None:
    bin_directory = run / "source" / ".pixi" / "envs" / "hpc" / "bin"
    bin_directory.mkdir(parents=True, exist_ok=True)
    _write_executable(
        bin_directory / "genome-to-diffraction",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mode=\n"
        "outdir=\n"
        "output=\n"
        "first_trace=\n"
        "resume_trace=\n"
        "manifest=\n"
        "verification_log=\n"
        "previous=\n"
        'case " $* " in\n'
        '  *" catalogue import "*) mode=catalogue ;;\n'
        '  *" structure-search qualify-p1 "*) mode=qualify ;;\n'
        '  *" phenix verify "*) mode=phenix ;;\n'
        '  *" databases prepare "*) mode=databases ;;\n'
        '  *" diffraction preflight "*) mode=preflight ;;\n'
        '  *" benchmark build-first-copy-controls "*) mode=control_bundle ;;\n'
        '  *" contract canonicalise "*) mode=canonicalise ;;\n'
        '  *" contract validate "*) mode=contract ;;\n'
        '  *" review build-mr-seed "*) mode=review ;;\n'
        "esac\n"
        'for argument in "$@"; do\n'
        '  [[ "$previous" != --outdir ]] || outdir="$argument"\n'
        '  [[ "$previous" != --output ]] || output="$argument"\n'
        '  [[ "$previous" != --first-trace ]] || first_trace="$argument"\n'
        '  [[ "$previous" != --resume-trace ]] || resume_trace="$argument"\n'
        '  [[ "$previous" != --manifest ]] || manifest="$argument"\n'
        '  [[ "$previous" != --verification-log ]] || '
        'verification_log="$argument"\n'
        '  previous="$argument"\n'
        "done\n"
        'if [[ "$mode" == catalogue ]]; then\n'
        '  [[ -n "$outdir" ]]\n'
        '  mkdir -p "$outdir"\n'
        "  printf '{}\\n' > \"$outdir/sequence_groups.jsonl\"\n"
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/catalogue_import_manifest.json"\n'
        "  printf '{}\\n' > \"$outdir/source_records.jsonl\"\n"
        'elif [[ "$mode" == qualify ]]; then\n'
        '  [[ -n "$output" && -f "$first_trace" && -f "$resume_trace" ]]\n'
        "  grep -q $'\\tCOMPLETED\\t' \"$first_trace\"\n"
        "  grep -q $'\\tCACHED\\t' \"$resume_trace\"\n"
        '  mkdir -p "$(dirname "$output")"\n'
        '  printf \'{"schema_version":"1.0","profile":"p1",'
        '"status":"passed","all_resume_processes_cached":true}\\n\' '
        '> "$output"\n'
        'elif [[ "$mode" == phenix ]]; then\n'
        '  [[ -n "$verification_log" ]]\n'
        "  printf 'verified\\n' > \"$verification_log\"\n"
        'elif [[ "$mode" == databases ]]; then\n'
        '  [[ -n "$manifest" ]]\n'
        "  printf '{}\\n' > \"$manifest\"\n"
        '  printf \'{"schema_version":"1.0","verification_level":'
        '"inventory_metadata_and_functional_smoke","full_checksums":false}\\n\' '
        '> "${manifest%.json}.verification.json"\n'
        'elif [[ "$mode" == contract ]]; then\n'
        '  [[ -f "${@: -1}" || -f "${@: -3:1}" ]]\n'
        'elif [[ "$mode" == canonicalise ]]; then\n'
        '  cat -- "${@: -3:1}"\n'
        'elif [[ "$mode" == preflight ]]; then\n'
        '  mkdir -p "$outdir"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/mtz_preflight.jsonl"\n'
        'elif [[ "$mode" == control_bundle ]]; then\n'
        '  mkdir -p "$outdir/hypotheses" "$outdir/models"\n'
        "  positive=mrhyp_"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "  negative=mrhyp_"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/control_pair_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/model_preparation_manifest.json"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/mr_hypotheses.jsonl"\n'
        '  printf \'{"hypothesis_id":"%s","priority_features":'
        '{"control_role":"known_positive"}}\\n\' "$positive" > '
        '"$outdir/hypotheses/${positive}.jsonl"\n'
        '  printf \'{"hypothesis_id":"%s","priority_features":'
        '{"control_role":"deliberate_unrelated_negative"}}\\n\' "$negative" > '
        '"$outdir/hypotheses/${negative}.jsonl"\n'
        'elif [[ "$mode" == review ]]; then\n'
        '  [[ -n "$outdir" ]]\n'
        '  mkdir -p "$outdir"\n'
        "  package_id=reviewpkg_"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "  printf 'rank\\tsolution_id\\n1\\tsol_%064d\\n' 1 > "
        '"$outdir/mr_seed_candidates.tsv"\n'
        "  printf '<html></html>\\n' > "
        '"$outdir/mr_seed_candidates.html"\n'
        "  printf 'solution_id\\nsol_%064d\\n' 1 > "
        '"$outdir/mr_seed_approval_candidates.tsv"\n'
        "  printf 'checkpoint\\titem_id\\tdecision\\treviewer\\t"
        "reviewed_at\\tcomment\\toverride_reason\\n' > "
        '"$outdir/approved_mr_seeds.tsv"\n'
        '  printf \'{\\n  "schema_version": "1.0",\\n  '
        '"package_id": "%s"\\n}\\n\' "$package_id" > '
        '"$outdir/mr_seed_review_manifest.json"\n'
        "else\n"
        "  exit 9\n"
        "fi\n",
    )
    _write_executable(
        bin_directory / "nextflow",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mode=discovery\n"
        "outdir=\n"
        "previous=\n"
        "status=COMPLETED\n"
        'printf \'%s\\n\' "$*" >> "$PWD/fake-nextflow-commands.log"\n'
        'for argument in "$@"; do\n'
        '  [[ "$argument" != */main.nf ]] || mode=p0\n'
        '  if [[ "$previous" == --qualification_stage ]]; then\n'
        '    case "$argument" in\n'
        "      prepare_predicted_models) mode=model ;;\n"
        "      prepare_experimental_models) mode=p2div-model ;;\n"
        "      first_copy) mode=p2 ;;\n"
        "      diverse_first_copy) mode=p2div ;;\n"
        "      first_copy_controls) mode=p2control ;;\n"
        "      discovery) mode=discovery ;;\n"
        "      *) exit 11 ;;\n"
        "    esac\n"
        "  fi\n"
        '  [[ "$previous" != --outdir ]] || outdir="$argument"\n'
        '  [[ "$argument" != -resume ]] || status=CACHED\n'
        '  previous="$argument"\n'
        "done\n"
        '[[ -n "$outdir" ]]\n'
        'mkdir -p "$outdir/pipeline_info"\n'
        "printf 'task_id\\tnative_id\\tname\\tstatus\\texit\\tduration\\t"
        "realtime\\t%%cpu\\tpeak_rss\\tpeak_vmem\\trchar\\twchar\\n' "
        '> "$outdir/pipeline_info/trace.tsv"\n'
        'if [[ "$mode" == p0 ]]; then\n'
        "  for task in 1 2 3 4; do printf '"
        "%s\\t123\\tP0_TASK\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$task" "$status"; done >> "$outdir/pipeline_info/trace.tsv"\n'
        'elif [[ "$mode" == p2 ]]; then\n'
        "  for task in 1 2; do printf '"
        "%s\\t123\\tP2_TASK\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$task" "$status"; done >> "$outdir/pipeline_info/trace.tsv"\n'
        'elif [[ "$mode" == p2div ]]; then\n'
        "  for task in 1 2 3; do printf '"
        "%s\\t123\\tP2_DIVERSE_TASK\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$task" "$status"; done >> "$outdir/pipeline_info/trace.tsv"\n'
        'elif [[ "$mode" == model ]]; then\n'
        "  process_name=PREPARE_PREDICTED_MODELS\n"
        "  printf '1\\t123\\t%s\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$process_name" "$status" >> "$outdir/pipeline_info/trace.tsv"\n'
        'elif [[ "$mode" == p2control ]]; then\n'
        "  for task in 1 2; do printf '"
        "%s\\t123\\tP2_CONTROL_TASK\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$task" "$status"; done >> "$outdir/pipeline_info/trace.tsv"\n'
        'elif [[ "$mode" == p2div-model ]]; then\n'
        "  process_name=PREPARE_EXPERIMENTAL_MODELS\n"
        "  printf '1\\t123\\t%s\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$process_name" "$status" >> "$outdir/pipeline_info/trace.tsv"\n'
        "else\n"
        "  process_name=SEARCH_PDB_SEQUENCES\n"
        "  printf '1\\t123\\t%s\\t%s\\t0\\t2s\\t1s\\t100%%%%\\t"
        "10 MB\\t20 MB\\t30 MB\\t4 MB\\n' "
        '"$process_name" "$status" >> "$outdir/pipeline_info/trace.tsv"\n'
        "fi\n"
        "for name in report.html timeline.html dag.html; do "
        "printf '<html></html>\\n' > \"$outdir/pipeline_info/$name\"; done\n"
        'if [[ "$mode" == p0 ]]; then\n'
        '  mkdir -p "$outdir/scope" "$outdir/catalogue" '
        '"$outdir/preflight" "$outdir/matthews"\n'
        "  printf '{}\\n' > \"$outdir/scope/pipeline_scope.json\"\n"
        "  printf '{}\\n' > "
        '"$outdir/catalogue/catalogue_import_manifest.json"\n'
        "  printf '{}\\n' > \"$outdir/preflight/mtz_preflight.jsonl\"\n"
        "  printf 'header\\n' > \"$outdir/preflight/mtz_preflight.tsv\"\n"
        "  printf '# preflight\\n' > "
        '"$outdir/preflight/preflight_report.md"\n'
        "  printf '{}\\n' > "
        '"$outdir/matthews/matthews_hypotheses.jsonl"\n'
        "  printf '# matthews\\n' > \"$outdir/matthews/matthews_report.md\"\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$mode" == p2 ]]; then\n'
        "  hypothesis=mrhyp_"
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd\n"
        '  p2_execution_status="${FAKE_P2_EXECUTION_STATUS:-completed_no_hit}"\n'
        '  result="$outdir/first_copy_phaser_${hypothesis}"\n'
        '  mkdir -p "$outdir/exact_predicted_funnel" "$result"\n'
        '  printf \'{"schema_version":"1.0"}\\n\' > '
        '"$outdir/exact_predicted_funnel/funnel_manifest.json"\n'
        '  printf \'{"hypothesis_id":"%s"}\\n\' "$hypothesis" > '
        '"$outdir/exact_predicted_funnel/mr_hypotheses.jsonl"\n'
        "  printf 'hypothesis_id\\n%s\\n' \"$hypothesis\" > "
        '"$outdir/exact_predicted_funnel/mr_hypotheses.tsv"\n'
        '  printf \'{"schema_version":"1.0","hypothesis_id":"%s",'
        '"tool_version":"fake","execution_status":"%s",'
        '"llg":null,"llgi":null,"tfz":null,"placed_copy_count":0,'
        '"packing_summary":{},"parser_warnings":[],"raw_log_pointer":'
        '"PHASER.log","preliminary_credibility_class":"no_solution",'
        '"rejection_reason":"fake_no_solution"}\\n\' '
        '"$hypothesis" "$p2_execution_status" > '
        '"$result/normalised_mr_result.json"\n'
        "  printf '{}\\n' > \"$result/phaser_command.json\"\n"
        "  printf 'fake Phaser log\\n' > \"$result/PHASER.log\"\n"
        "  printf 'fake capture\\n' > "
        '"$result/phenix.phaser.capture.log"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$mode" == p2div ]]; then\n'
        '  p2_execution_status="${FAKE_P2_DIVERSE_EXECUTION_STATUS:-'
        'completed_no_hit}"\n'
        '  funnel="$outdir/diverse_first_copy_funnel"\n'
        '  mkdir -p "$funnel"\n'
        '  printf \'{"schema_version":"1.0","selected_hypothesis_count":2}\\n\' '
        '> "$funnel/funnel_manifest.json"\n'
        '  : > "$funnel/mr_hypotheses.jsonl"\n'
        "  printf 'hypothesis_id\\n' > \"$funnel/mr_hypotheses.tsv\"\n"
        "  for suffix in 1 2; do\n"
        "    hypothesis=mrhyp_$(printf '%064d' \"$suffix\")\n"
        "    source_class=experimental\n"
        '    [[ "$suffix" != 1 ]] || source_class=predicted\n'
        '    printf \'{"hypothesis_id":"%s","priority_features":'
        '{"structural_source_class":"%s"}}\\n\' '
        '"$hypothesis" "$source_class" >> "$funnel/mr_hypotheses.jsonl"\n'
        '    printf \'%s\\n\' "$hypothesis" >> "$funnel/mr_hypotheses.tsv"\n'
        '    result="$outdir/first_copy_phaser_${hypothesis}"\n'
        '    mkdir -p "$result"\n'
        '    printf \'{"schema_version":"1.0","hypothesis_id":"%s",'
        '"tool_version":"fake","execution_status":"%s",'
        '"llg":null,"llgi":null,"tfz":null,"placed_copy_count":0,'
        '"packing_summary":{},"parser_warnings":[],"raw_log_pointer":'
        '"PHASER.log","preliminary_credibility_class":"no_solution",'
        '"rejection_reason":"fake_no_solution"}\\n\' '
        '"$hypothesis" "$p2_execution_status" > '
        '"$result/normalised_mr_result.json"\n'
        '    cp "$result/normalised_mr_result.json" '
        '"$result/normalised_mr_result.jsonl"\n'
        "    printf '{}\\n' > \"$result/phaser_command.json\"\n"
        "    printf 'fake diverse Phaser log\\n' > \"$result/PHASER.log\"\n"
        "    printf 'fake diverse capture\\n' > "
        '"$result/phenix.phaser.capture.log"\n'
        "  done\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$mode" == p2control ]]; then\n'
        "  for role in positive negative; do\n"
        '    if [[ "$role" == positive ]]; then\n'
        "      hypothesis=mrhyp_"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        '      payload=\'{"execution_status":"completed_hit",'
        '"hypothesis_id":"\'$hypothesis\'",'
        '"llg":1149.2,"tfz":46.0,"placed_copy_count":1,"packing_summary":'
        '{"top_solution_packed":true,"score_gate_passed":true}}\'\n'
        "    else\n"
        "      hypothesis=mrhyp_"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        '      payload=\'{"execution_status":"completed_hit",'
        '"hypothesis_id":"\'$hypothesis\'",'
        '"llg":30.1,"tfz":6.8,"placed_copy_count":1,"packing_summary":'
        '{"top_solution_packed":true,"score_gate_passed":true}}\'\n'
        "    fi\n"
        '    result="$outdir/first_copy_phaser_${hypothesis}"\n'
        '    mkdir -p "$result"\n'
        '    printf \'%s\\n\' "$payload" > "$result/normalised_mr_result.jsonl"\n'
        '    printf \'%s\\n\' "$payload" > "$result/normalised_mr_result.json"\n'
        '    printf \'{"arguments":["phenix.phaser"]}\\n\' > '
        '"$result/phaser_command.json"\n'
        "    printf 'fake control Phaser log\\n' > \"$result/PHASER.log\"\n"
        "  done\n"
        "  exit 0\n"
        "fi\n"
        'if [[ "$mode" == model ]]; then\n'
        '  mkdir -p "$outdir/predicted_model_preparation"\n'
        '  printf \'{"schema_version":"1.0","model_id":"model_test"}\\n\' '
        '> "$outdir/predicted_model_preparation/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0","processed_model_count":1}\\n\' '
        '> "$outdir/predicted_model_preparation/model_preparation_manifest.json"\n'
        "  exit 0\n"
        "fi\n"
        'if [[ "$mode" == p2div-model ]]; then\n'
        '  mkdir -p "$outdir/experimental_model_preparation"\n'
        '  printf \'{"schema_version":"1.0","model_id":"pdb_model_test"}\\n\' '
        '> "$outdir/experimental_model_preparation/processed_models.jsonl"\n'
        '  printf \'{"schema_version":"1.0","processed_model_count":1}\\n\' '
        '> "$outdir/experimental_model_preparation/model_preparation_manifest.json"\n'
        "  exit 0\n"
        "fi\n"
        'mkdir -p "$outdir/pdb_sequence_search/raw" '
        '"$outdir/afdb_exact_search/raw"\n'
        'printf \'{"schema_version":"1.0",'
        '"provider":"pdb_sequence_mmseqs"}\\n\' '
        '> "$outdir/pdb_sequence_search/search_manifest.json"\n'
        "printf 'fake mmseqs log\\n' > "
        '"$outdir/pdb_sequence_search/raw/mmseqs.log"\n'
        'printf \'{"schema_version":"1.0"}\\n\' '
        '> "$outdir/pdb_sequence_search/structural_hits.jsonl"\n'
        'printf \'{"schema_version":"1.0"}\\n\' '
        '> "$outdir/afdb_exact_search/coordinate_sources.jsonl"\n',
    )


def test_p1_job_uses_fixed_real_search_profile_and_collects_qualification(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)

    readiness = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p1"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert readiness["profile"] == "p1"
    assert readiness["ready"] == "true"

    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                P1_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "p1",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "p1"
    run = remote_root / "runs" / P1_RUN_ID
    login_prefetch_log = (run / "logs/p1-login-prefetch.log").read_text(
        encoding="utf-8"
    )
    assert "phase=p1_login_catalogue_import profile=p1" in login_prefetch_log
    assert "phase=p1_login_provider_plan profile=p1" in login_prefetch_log
    assert "phase=p1_login_afdb_prefetch profile=p1" in login_prefetch_log
    assert (run / "artifacts/p1/provider-plan/provider_plan.json").is_file()
    assert (run / "state/p1-login-prefetch.sha256").is_file()
    assert (run / "artifacts/p1/afdb-login-prefetch/coordinate_sources.jsonl").is_file()
    _install_fake_p1_runtime(run)

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", P1_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["job_id"] == "123"
    submitted_arguments = (
        (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    )
    assert "--cpus-per-task=2" in submitted_arguments
    assert "--mem=8G" in submitted_arguments
    assert "--time=24:00:00" in submitted_arguments

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    _run(
        [str(smoke_job), P1_RUN_ID, str(remote_root), "p1"],
        cwd=tmp_path,
        environment=job_environment,
    )

    result = json.loads((run / "state/job-result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == "success"
    qualification = json.loads(
        (run / "artifacts/qualification/p1-qualification.json").read_text(
            encoding="utf-8"
        )
    )
    assert qualification["status"] == "passed"
    assert qualification["all_resume_processes_cached"] is True
    p1_log = (run / "logs/p1.log").read_text(encoding="utf-8")
    assert "phase=p1_first_run profile=p1" in p1_log
    assert "phase=p1_resume_run profile=p1" in p1_log
    assert "p1_status=direct_pdb_sequence_search_qualified" in p1_log
    assert (
        "prostt5_foldseek_status=pilot_slice_complete_full_catalogue_pending" in p1_log
    )
    assert "phase=p1_model_first_run profile=p1" in p1_log
    assert "phase=p1_model_resume_run profile=p1" in p1_log
    assert "phase=p1_login_prefetch_verify profile=p1" in p1_log
    assert "afdb_exact_status=login_prefetch_verified_compute_offline" in p1_log
    assert "predicted_model_status=confidence_processed_and_resume_cached" in p1_log
    nextflow_commands = (run / "execution/fake-nextflow-commands.log").read_text(
        encoding="utf-8"
    )
    assert "--afdb_accession_map" not in nextflow_commands
    assert "qualification.nf --qualification_stage prepare_predicted_models" in (
        nextflow_commands
    )
    assert "--phenix_manifest" in nextflow_commands

    archive_path = tmp_path / "p1-collected.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", P1_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
    assert "artifacts/qualification/p1-qualification.json" in names
    assert "artifacts/qualification/p1-resume-pipeline-info/trace.tsv" in names
    assert "artifacts/qualification/p1-model-resume-check.json" in names
    assert "artifacts/qualification/p1-model-resume-pipeline-info/trace.tsv" in names
    assert "artifacts/p1/discovery/pdb_sequence_search/search_manifest.json" in names
    assert "artifacts/p1/discovery/pdb_sequence_search/raw/mmseqs.log" in names
    assert (
        "artifacts/p1/model-preparation/predicted_model_preparation/"
        "model_preparation_manifest.json"
    ) in names
    assert (
        "artifacts/p1/model-preparation/predicted_model_preparation/"
        "processed_models.jsonl"
    ) in names
    assert "state/p1-login-prefetch.sha256" in names
    assert "logs/p1-login-prefetch.log" in names
    assert "artifacts/p1/provider-plan/provider_plan.json" in names
    assert "artifacts/p1/provider-plan/entries/afdb_exact.json" in names
    assert "artifacts/p1/provider-plan/entries/pdb_sequence.json" in names
    assert "artifacts/p1/afdb-login-prefetch/search_manifest.json" in names
    assert "artifacts/p1/afdb-login-prefetch/coordinate_sources.jsonl" in names


def test_p1_stage_refuses_missing_reviewed_provider_plan(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _write_p0_paths(smoke_job.parent.parent)
    failing_environment = dict(environment)
    failing_environment["FAKE_PROVIDER_PLAN_FAIL"] = "1"

    failed = _run(
        [
            str(dispatcher),
            "stage",
            P1_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p1",
        ],
        cwd=tmp_path,
        environment=failing_environment,
        success=False,
    )

    assert _decode_protocol(failed.stdout)["failure_class"] == "software_failure"
    run = smoke_job.parent.parent / "runs" / P1_RUN_ID
    assert (run / "state/phase").read_text(encoding="ascii").strip() == ("stage_failed")
    assert not (run / "artifacts/p1/afdb-login-prefetch").exists()


def test_p1_stage_classifies_login_node_afdb_transfer_failure(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _write_p0_paths(smoke_job.parent.parent)
    failing_environment = dict(environment)
    failing_environment["FAKE_AFDB_PREFETCH_FAIL"] = "1"

    failed = _run(
        [
            str(dispatcher),
            "stage",
            P1_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p1",
        ],
        cwd=tmp_path,
        environment=failing_environment,
        success=False,
    )

    assert _decode_protocol(failed.stdout)["failure_class"] == "transfer_failure"
    run = smoke_job.parent.parent / "runs" / P1_RUN_ID
    assert (run / "state/phase").read_text(encoding="ascii").strip() == ("stage_failed")
    assert (run / "state/failure-class").read_text(encoding="ascii").strip() == (
        "transfer_failure"
    )
    log = (run / "logs/p1-login-prefetch.log").read_text(encoding="utf-8")
    assert "phase=p1_login_afdb_prefetch profile=p1" in log


def test_p2_stage_and_submit_are_fixed_and_reuse_verified_prefetch(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)

    readiness = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p2"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert readiness["profile"] == "p2"
    assert readiness["ready"] == "true"

    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                P2_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "p2",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "p2"
    run = remote_root / "runs" / P2_RUN_ID
    prefetch_log = (run / "logs/p1-login-prefetch.log").read_text(encoding="utf-8")
    assert "phase=p1_login_catalogue_import profile=p2" in prefetch_log
    assert "phase=p1_login_afdb_prefetch profile=p2" in prefetch_log
    assert (run / "state/p1-login-prefetch.sha256").is_file()

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", P2_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["profile"] == "p2"
    arguments = (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    assert "--cpus-per-task=2" in arguments
    assert "--mem=8G" in arguments
    assert "--time=24:00:00" in arguments
    assert arguments[-4:] == [str(smoke_job), P2_RUN_ID, str(remote_root), "p2"]


def test_p2_job_runs_fixed_cd6_first_copy_and_collects_normalised_result(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    _run(
        [
            str(dispatcher),
            "stage",
            P2_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p2",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    run = remote_root / "runs" / P2_RUN_ID
    _install_fake_p1_runtime(run)
    _run(
        [str(dispatcher), "submit", P2_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    _run(
        [str(smoke_job), P2_RUN_ID, str(remote_root), "p2"],
        cwd=tmp_path,
        environment=job_environment,
    )

    job_result = json.loads((run / "state/job-result.json").read_text(encoding="utf-8"))
    assert job_result["failure_class"] == "success"
    assert job_result["profile"] == "p2"
    result = json.loads(
        (run / "artifacts/qualification/p2-first-copy-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["execution_status"] == "completed_no_hit"
    resume = json.loads(
        (run / "artifacts/qualification/p2-first-copy-resume-check.json").read_text(
            encoding="utf-8"
        )
    )
    assert resume["crystal_id"] == "CD6QS2P2G1_5"
    assert resume["process_count"] == 2
    assert resume["cached_process_count"] == 2
    p2_log = (run / "logs/p2.log").read_text(encoding="utf-8")
    assert "phase=p2_replay_p0 profile=p2" in p2_log
    assert "phase=p2_replay_p1 profile=p2" in p2_log
    assert "phase=p2_first_copy_first_run profile=p2" in p2_log
    assert "phase=p2_first_copy_resume_run profile=p2" in p2_log
    assert "p2_status=cd6_first_copy_completed_and_resume_cached" in p2_log

    archive_path = tmp_path / "p2-collected.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", P2_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
    assert "artifacts/qualification/p2-first-copy-result.json" in names
    assert "artifacts/qualification/p2-first-copy-command.json" in names
    assert "artifacts/qualification/p2-first-copy-PHASER.log" in names
    assert (
        "artifacts/qualification/p2-first-copy-resume-pipeline-info/trace.tsv" in names
    )
    assert "artifacts/p2/first-copy/exact_predicted_funnel/mr_hypotheses.jsonl" in names


def test_p2_job_rejects_adapter_failure_as_test_failure(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    _run(
        [
            str(dispatcher),
            "stage",
            P2_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p2",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    run = remote_root / "runs" / P2_RUN_ID
    _install_fake_p1_runtime(run)
    _run(
        [str(dispatcher), "submit", P2_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment["FAKE_P2_EXECUTION_STATUS"] = "failed_tool_execution"
    completed = _run(
        [str(smoke_job), P2_RUN_ID, str(remote_root), "p2"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )

    assert completed.returncode == 4
    job_result = json.loads((run / "state/job-result.json").read_text(encoding="utf-8"))
    assert job_result["failure_class"] == "test_failure"
    result = json.loads(
        (run / "artifacts/qualification/p2-first-copy-result.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["execution_status"] == "failed_tool_execution"
    assert not (
        run / "artifacts/qualification/p2-first-copy-resume-check.json"
    ).exists()


def test_p2_control_stages_fixed_public_inputs_and_submits_closed_profile(
    tmp_path: Path,
) -> None:
    dispatcher, _smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent
    _write_p0_paths(remote_root)

    readiness = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p2-control"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert readiness["profile"] == "p2-control"
    assert readiness["ready"] == "true"
    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                P2_CONTROL_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "p2-control",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "p2-control"
    run = remote_root / "runs" / P2_CONTROL_RUN_ID
    assert (run / "state/p2-control-login-stage.sha256").is_file()
    login_log = (run / "logs/p2-control-login-stage.log").read_text(encoding="utf-8")
    assert "phase=p2_control_prepare_public_control" in login_log
    assert (run / "artifacts/p2-control/catalogue/sequence_groups.jsonl").is_file()
    _install_fake_p1_runtime(run)
    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", P2_CONTROL_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["profile"] == "p2-control"
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    _run(
        [
            str(_smoke_job),
            P2_CONTROL_RUN_ID,
            str(remote_root),
            "p2-control",
        ],
        cwd=tmp_path,
        environment=job_environment,
    )
    job_result = json.loads((run / "state/job-result.json").read_text(encoding="utf-8"))
    assert job_result["failure_class"] == "success"
    summary = json.loads(
        (run / "artifacts/qualification/p2-control-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["all_parsed_solutions_retained"] is True
    assert summary["positive_outranks_unrelated_negative"] is True
    assert summary["positive"]["execution_status"] == "completed_hit"
    assert summary["negative"]["execution_status"] == "completed_hit"
    assert (run / "artifacts/qualification/p2-control-commands.jsonl").is_file()
    assert (run / "artifacts/qualification/p2-control-artifact-sha256.tsv").is_file()
    archive = _run(
        [str(dispatcher), "collect", P2_CONTROL_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    assert "artifacts/qualification/p2-control-summary.json" in names
    assert "artifacts/qualification/p2-control-commands.jsonl" in names
    assert "artifacts/qualification/p2-control-artifact-sha256.tsv" in names


def test_phase3_phenix_probe_is_fixed_and_collectable(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent
    p0_paths = _write_p0_paths(remote_root)
    phenix_manifest = Path(p0_paths.read_text(encoding="ascii").splitlines()[6])
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    p0_paths.unlink()

    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                PHASE3_PHENIX_PROBE_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "phase3-phenix-probe",
                str(phenix_manifest),
                phenix_sha256,
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "phase3-phenix-probe"
    run = remote_root / "runs" / PHASE3_PHENIX_PROBE_RUN_ID

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", PHASE3_PHENIX_PROBE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["profile"] == "phase3-phenix-probe"
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    _run(
        [
            str(smoke_job),
            PHASE3_PHENIX_PROBE_RUN_ID,
            str(remote_root),
            "phase3-phenix-probe",
        ],
        cwd=tmp_path,
        environment=job_environment,
    )

    result = json.loads((run / "state/job-result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == "success"
    probe = json.loads(
        (run / "artifacts/qualification/phaser-interface-probe.json").read_text(
            encoding="utf-8"
        )
    )
    assert probe["scientific_execution_performed"] is False
    assert (run / "artifacts/qualification/phenix-phaser-show-defaults.txt").is_file()
    assert (
        run / "artifacts/qualification/phase3-phenix-probe-checksums.sha256"
    ).is_file()

    archive = _run(
        [str(dispatcher), "collect", PHASE3_PHENIX_PROBE_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    assert "artifacts/qualification/phaser-interface-probe.json" in names
    assert "artifacts/qualification/phenix-phaser-show-defaults.txt" in names
    assert "artifacts/qualification/phase3-phenix-probe-checksums.sha256" in names


def test_phase3_network_probe_stages_only_the_tracked_marmic_policy(
    tmp_path: Path,
) -> None:
    dispatcher, _smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent

    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                PHASE3_NETWORK_PROBE_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "phase3-network-probe",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )

    assert staged["profile"] == "phase3-network-probe"
    run = remote_root / "runs" / PHASE3_NETWORK_PROBE_RUN_ID
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    contract = manifest["phase3_network_site_contract"]
    assert contract["nextflow_profile"] == "marmic"
    assert contract["site_config"] == "conf/marmic.config"
    assert contract["worker_shell"] == "bootstrap/nf-gtd-worker-offline-shell"
    assert (
        contract["site_config_sha256"]
        == hashlib.sha256((run / "source/conf/marmic.config").read_bytes()).hexdigest()
    )
    assert (
        contract["worker_shell_sha256"]
        == hashlib.sha256(
            (run / "source/bootstrap/nf-gtd-worker-offline-shell").read_bytes()
        ).hexdigest()
    )

    submitted = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "submit",
                PHASE3_NETWORK_PROBE_RUN_ID,
                OWNER_ID,
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["profile"] == "phase3-network-probe"
    arguments = (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    assert "--cpus-per-task=2" in arguments
    assert "--mem=8G" in arguments
    assert "--time=00:45:00" in arguments


def test_phase3_network_probe_uses_the_canonical_qualification_root() -> None:
    wrapper = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(
        encoding="utf-8"
    )
    phase = wrapper.split("run_phase3_network_probe() {", maxsplit=1)[1]
    invocation = phase.split("\n}\n", maxsplit=1)[0]

    assert 'run "$RUN/source/qualification.nf"' in invocation
    assert "--qualification_stage phase3_network_probe" in invocation
    assert '--cache_root "$RUN/cache/phase3-network-probe"' in invocation
    assert "-main-script workflows/qualification/phase3_network_probe.nf" not in (
        invocation
    )


def test_heteromer_multicopy_partner_preserves_parent_model_uncertainty() -> None:
    wrapper = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(
        encoding="utf-8"
    )
    phase = wrapper.split(
        "printf 'phase=heteromer_multicopy_partner_B profile=heteromer-smoke\\n'",
        maxsplit=1,
    )[1]
    invocation = phase.split("\n\n", maxsplit=1)[0]

    assert (
        '--parent-model-identity-fraction "$multicopy_parent_model_identity_fraction"'
        in invocation
    )
    assert (
        '--parent-model-uncertainty-source "$multicopy_parent_model_uncertainty_source"'
        in invocation
    )


def test_heteromer_wrong_partner_preserves_parent_model_uncertainty() -> None:
    wrapper = (REPOSITORY / "bootstrap/nf-gtd-hpc-smoke-job").read_text(
        encoding="utf-8"
    )
    phase = wrapper.split(
        "printf 'phase=heteromer_p6_wrong_partner profile=heteromer-smoke\\n'",
        maxsplit=1,
    )[1]
    invocation = phase.split("\n    mapfile", maxsplit=1)[0]

    assert (
        '--parent-model-identity-fraction "$parent_model_identity_fraction"'
        in invocation
    )
    assert (
        '--parent-model-uncertainty-source "$parent_model_uncertainty_source"'
        in invocation
    )


def test_heteromer_smoke_runs_6rtz_checkpoint_and_3u7q_joint_copy_chain(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent
    p0_paths = _write_p0_paths(remote_root)
    phenix_manifest = Path(p0_paths.read_text(encoding="ascii").splitlines()[6])
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    p0_paths.unlink()

    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                HETEROMER_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "heteromer-smoke",
                str(phenix_manifest),
                phenix_sha256,
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "heteromer-smoke"
    run = remote_root / "runs" / HETEROMER_RUN_ID
    assert (run / "state/heteromer-login-stage.sha256").is_file()
    assert (
        run / "artifacts/heteromer-smoke/inputs/preparation_manifest.json"
    ).is_file()
    assert (
        run / "artifacts/heteromer-smoke/inputs/multicopy/preparation_manifest.json"
    ).is_file()
    assert (
        run
        / "artifacts/heteromer-smoke/inputs/phase3-control/preparation_manifest.json"
    ).is_file()
    assert (
        run
        / "artifacts/heteromer-smoke/inputs/catalogue-control/preparation_manifest.json"
    ).is_file()
    assert (
        run / "artifacts/heteromer-smoke/inputs/p6-control/preparation_manifest.json"
    ).is_file()
    p6_inputs = run / "artifacts/heteromer-smoke/inputs/p6-control"
    p6_preparation = json.loads(
        (p6_inputs / "preparation_manifest.json").read_text(encoding="utf-8")
    )
    assert p6_preparation["adapter_version"] == "heteromer-p6-control-slice-v2"
    assert (
        p6_preparation["protocol"]["sha256"]
        == hashlib.sha256(
            (run / "source/benchmarks/m6/protocol.yaml").read_bytes()
        ).hexdigest()
    )
    for crystal_id, relative in (
        ("6RTZ", "../preparation_manifest.json"),
        ("3U7Q", "../multicopy/preparation_manifest.json"),
    ):
        source = (p6_inputs / relative).resolve()
        assert (
            p6_preparation["source_preparations"][crystal_id]["manifest_sha256"]
            == hashlib.sha256(source.read_bytes()).hexdigest()
        )
    missing_model_relative = p6_preparation["files"]["missing_parent_model"]["path"]
    missing_model = p6_inputs / missing_model_relative
    assert missing_model.is_file()
    assert (
        missing_model.name
        == f"{hashlib.sha256(missing_model.read_bytes()).hexdigest()}.pdb"
    )
    scope_decision = json.loads(
        (p6_inputs / "component_scope_decision.json").read_text(encoding="utf-8")
    )
    assert scope_decision["status"] == "unsupported_component_count"
    assert scope_decision["complete_composition_claim_eligible"] is False
    staged_paths = {
        line.split(maxsplit=1)[1]
        for line in (run / "state/heteromer-login-stage.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    assert str(missing_model) in staged_paths
    assert str(p6_inputs / "component_scope_decision.json") in staged_paths
    assert str(p6_inputs / "wrong_partner/sequence_groups.jsonl") in staged_paths
    assert str(p6_inputs / "wrong_partner/model.pdb") in staged_paths
    assert (
        str(run / "artifacts/heteromer-smoke/inputs/phase3-control/derived/9ECN.mtz")
        in staged_paths
    )

    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", HETEROMER_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["profile"] == "heteromer-smoke"
    arguments = (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    assert "--cpus-per-task=8" in arguments
    assert "--mem=32G" in arguments
    assert "--time=24:00:00" in arguments

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_CPUS_PER_TASK"] = "8"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    _run(
        [str(smoke_job), HETEROMER_RUN_ID, str(remote_root), "heteromer-smoke"],
        cwd=tmp_path,
        environment=job_environment,
    )

    summary = json.loads(
        (run / "artifacts/qualification/heteromer-smoke-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["gate_passed"] is True
    assert summary["incremental_llg"] == 150.0
    assert summary["partner_tfz"] == 12.0
    multicopy = json.loads(
        (run / "artifacts/qualification/heteromer-multicopy-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert multicopy["gate_passed"] is True
    assert multicopy["parent_copy_count"] == 2
    assert multicopy["requested_partner_copy_count"] == 2
    assert multicopy["partner_placement_count"] == 2
    catalogue = json.loads(
        (run / "artifacts/qualification/heteromer-catalogue-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert catalogue["gate_passed"] is True
    assert catalogue["candidate_count"] == 1845
    assert catalogue["selected_attempt_count"] == 1
    assert catalogue["unsearchable_candidate_count"] == 1844
    p6 = json.loads(
        (run / "artifacts/qualification/heteromer-control-slice-report.json").read_text(
            encoding="utf-8"
        )
    )
    assert p6["gate_passed"] is True
    assert (
        p6["cases"]["missing_B"]["assessment"]["complete_composition_claimed"] is False
    )
    assert (
        p6["cases"]["wrong_B"]["assessment"]["scientific_status"]
        == "search_evidence_only"
    )
    assert (
        p6["cases"]["9ECN_three_component_boundary"]["status"]
        == "unsupported_component_count"
    )
    missing_plan = run / "artifacts/heteromer-smoke/p6/missing-plan"
    missing_candidates = [
        json.loads(line)
        for line in (missing_plan / "partner_candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(missing_candidates) == 1845
    assert len({row["candidate_id"] for row in missing_candidates}) == 1845
    missing_summary = json.loads(
        (run / "artifacts/heteromer-smoke/p6/missing-partner-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert missing_summary["candidate_count"] == 1845
    assert (
        missing_summary["plan_sha256"]
        == hashlib.sha256(
            (missing_plan / "partner_search_plan.json").read_bytes()
        ).hexdigest()
    )
    assessments = [
        json.loads(line)
        for line in (
            run / "artifacts/qualification/heteromer-composition-assessments.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(assessments) == 6
    assert all(row["complete_composition_claimed"] is False for row in assessments)
    assert (
        next(row for row in assessments if row["case_id"] == "wrong_B")[
            "scientific_status"
        ]
        == "search_evidence_only"
    )
    checksum_paths = {
        line.split(maxsplit=1)[1]
        for line in (run / "artifacts/qualification/heteromer-smoke-checksums.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    expected_p6_checksums = {
        "artifacts/heteromer-smoke/inputs/p6-control/component_scope_decision.json",
        f"artifacts/heteromer-smoke/inputs/p6-control/{missing_model_relative}",
        "artifacts/heteromer-smoke/p6/missing-plan/partner_candidates.jsonl",
        "artifacts/heteromer-smoke/p6/wrong-partner/partner_search_result.json",
        "artifacts/heteromer-smoke/p6/wrong-partner/partner_search_result.jsonl",
        "artifacts/heteromer-smoke/p6/wrong-partner/phaser_command.json",
        "artifacts/heteromer-smoke/p6/wrong-partner/partner_search.eff",
        "artifacts/heteromer-smoke/p6/wrong-partner/PHASER.log",
        "artifacts/heteromer-smoke/p6/wrong-partner/phenix.phaser.capture.log",
        "artifacts/heteromer-smoke/p6/wrong-partner/PHASER.1.pdb",
        "artifacts/heteromer-smoke/p6/wrong-partner/PHASER.1.mtz",
        "artifacts/qualification/heteromer-control-slice-report.json",
        "artifacts/qualification/heteromer-composition-assessments.jsonl",
    }
    assert expected_p6_checksums <= checksum_paths
    placement_checksum_paths = {
        line.split(maxsplit=1)[1]
        for line in (
            run / "artifacts/qualification/phase3-placement-control-checksums.sha256"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    }
    assert len(placement_checksum_paths) == 46
    assert {
        "artifacts/heteromer-smoke/partner/PHASER.sol",
        "artifacts/heteromer-smoke/partner/component_A.pdb",
        "artifacts/heteromer-smoke/partner/component_B.pdb",
        "artifacts/heteromer-smoke/partner/phaser_per_placement_inventory.json",
        "artifacts/heteromer-smoke/multicopy/partner/PHASER.sol",
        "artifacts/heteromer-smoke/multicopy/partner/component_A.pdb",
        "artifacts/heteromer-smoke/multicopy/partner/component_B.pdb",
        "artifacts/heteromer-smoke/multicopy/partner/phaser_per_placement_inventory.json",
        "artifacts/qualification/phase3-placement-control-summary.json",
    } <= placement_checksum_paths
    placement_summary = json.loads(
        (
            run / "artifacts/qualification/phase3-placement-control-summary.json"
        ).read_text(encoding="utf-8")
    )
    assert placement_summary["component_mapping_passed"] is True
    assert placement_summary["recombination_qualified"] is True
    assert [row["crystal_id"] for row in placement_summary["controls"]] == [
        "3U7Q",
        "6RTZ",
    ]
    phase3_control_root = run / "artifacts/heteromer-smoke/phase3-control"
    phase3_control = json.loads(
        (phase3_control_root / "phase3-9ecn-control-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert phase3_control["gate_passed"] is True
    assert phase3_control["component_copy_counts"] == {"A": 2, "B": 2, "C": 2}
    assert phase3_control["exact_identity_claimed_by_search"] is False
    assert phase3_control["complete_composition_claimed_by_search"] is False
    phase3_checksum_paths = {
        line.split(maxsplit=1)[1]
        for line in (phase3_control_root / "phase3-9ecn-control-checksums.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    assert len(phase3_checksum_paths) >= 20
    assert {
        "partner_B/phaser_per_placement_inventory.json",
        "component_C/component_search_result.json",
        "component_C/phaser_per_placement_inventory.json",
        "phase3-9ecn-control-summary.json",
    } <= phase3_checksum_paths
    log = (run / "logs/heteromer-smoke.log").read_text(encoding="utf-8")
    assert "phase=heteromer_parent_A profile=heteromer-smoke" in log
    assert "phase=heteromer_component_review profile=heteromer-smoke" in log
    assert "phase=heteromer_partner_B profile=heteromer-smoke" in log
    assert (
        "phase=heteromer_partner_component_coordinates profile=heteromer-smoke" in log
    )
    assert "phase=heteromer_multicopy_parent_A profile=heteromer-smoke" in log
    assert "phase=heteromer_multicopy_partner_B profile=heteromer-smoke" in log
    assert (
        "phase=heteromer_multicopy_component_coordinates profile=heteromer-smoke" in log
    )
    assert "phase=heteromer_catalogue_plan profile=heteromer-smoke" in log
    assert "phase=heteromer_catalogue_partner profile=heteromer-smoke" in log
    assert "phase=heteromer_p6_missing_partner profile=heteromer-smoke" in log
    assert "phase=heteromer_p6_wrong_partner profile=heteromer-smoke" in log
    assert "phase=heteromer_p6_gate profile=heteromer-smoke" in log
    assert "phase=heteromer_phase3_9ecn profile=heteromer-smoke" in log

    archive = _run(
        [str(dispatcher), "collect", HETEROMER_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        member_names = collected.getnames()
    assert len(member_names) == len(set(member_names))
    names = set(member_names)
    assert "artifacts/qualification/heteromer-smoke-summary.json" in names
    assert "artifacts/qualification/heteromer-multicopy-summary.json" in names
    assert "artifacts/qualification/heteromer-catalogue-summary.json" in names
    assert "artifacts/qualification/heteromer-control-slice-report.json" in names
    assert "artifacts/qualification/heteromer-composition-assessments.jsonl" in names
    assert "artifacts/qualification/phase3-placement-control-summary.json" in names
    assert "artifacts/qualification/phase3-placement-control-checksums.sha256" in names
    assert (
        "artifacts/heteromer-smoke/phase3-control/phase3-9ecn-control-summary.json"
        in names
    )
    assert (
        "artifacts/heteromer-smoke/phase3-control/phase3-9ecn-control-checksums.sha256"
        in names
    )
    assert (
        "artifacts/heteromer-smoke/phase3-control/component_C/"
        "phaser_per_placement_inventory.json" in names
    )
    assert "artifacts/heteromer-smoke/parent/normalised_mr_result.json" in names
    assert (
        "artifacts/heteromer-smoke/component_checkpoint/approved_mr_seed_stage/"
        "live_m4_stage_manifest.json"
    ) in names
    assert "artifacts/heteromer-smoke/partner/partner_search_result.json" in names
    assert "artifacts/heteromer-smoke/partner/PHASER.sol" in names
    assert "artifacts/heteromer-smoke/partner/component_A.pdb" in names
    assert "artifacts/heteromer-smoke/partner/component_B.pdb" in names
    assert "artifacts/heteromer-smoke/partner/PHASER.1.1.pdb" not in names
    assert (
        "artifacts/heteromer-smoke/partner/phaser_per_placement_inventory.json" in names
    )
    assert "artifacts/heteromer-smoke/p6/missing-plan/partner_search_plan.json" in names
    assert "artifacts/heteromer-smoke/p6/missing-partner-summary.json" in names
    assert (
        "artifacts/heteromer-smoke/inputs/p6-control/component_scope_decision.json"
        in names
    )
    assert (
        f"artifacts/heteromer-smoke/inputs/p6-control/{missing_model_relative}" in names
    )
    assert (
        "artifacts/heteromer-smoke/p6/wrong-partner/partner_search_result.json" in names
    )
    for relative in (
        "phaser_command.json",
        "partner_search.eff",
        "PHASER.log",
        "phenix.phaser.capture.log",
        "PHASER.1.pdb",
        "PHASER.1.mtz",
    ):
        assert f"artifacts/heteromer-smoke/p6/wrong-partner/{relative}" in names
    assert (
        "artifacts/heteromer-smoke/multicopy/partner/partner_search_result.json"
        in names
    )
    for relative in (
        "PHASER.sol",
        "component_A.pdb",
        "component_B.pdb",
        "phaser_per_placement_inventory.json",
    ):
        assert f"artifacts/heteromer-smoke/multicopy/partner/{relative}" in names
    assert "artifacts/heteromer-smoke/catalogue/plan/partner_search_plan.json" in names
    assert (
        "artifacts/heteromer-smoke/catalogue/partner/partner_search_result.json"
        in names
    )
    assert "artifacts/heteromer-smoke/catalogue/partner_attempt_summary.json" in names


def test_heteromer_collection_allowlist_has_no_duplicate_p6_report() -> None:
    dispatcher = (REPOSITORY / "bootstrap/nf-gtd-hpc-remote").read_text(
        encoding="utf-8"
    )

    assert (
        dispatcher.count(
            "        artifacts/qualification/heteromer-control-slice-report.json \\"
        )
        == 1
    )


def test_heteromer_collection_accepts_large_3u7q_mtz_evidence(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent
    p0_paths = _write_p0_paths(remote_root)
    phenix_manifest = Path(p0_paths.read_text(encoding="ascii").splitlines()[6])
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    p0_paths.unlink()
    _run(
        [
            str(dispatcher),
            "stage",
            HETEROMER_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "heteromer-smoke",
            str(phenix_manifest),
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    run = remote_root / "runs" / HETEROMER_RUN_ID
    fixed_paths = (
        "artifacts/heteromer-smoke/inputs/multicopy/derived/3U7Q.mtz",
        "artifacts/heteromer-smoke/multicopy/partner/PHASER.1.mtz",
    )
    for relative in fixed_paths:
        path = run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        os.truncate(path, 20 * 1024 * 1024 + 1)

    archive = _run(
        [str(dispatcher), "collect", HETEROMER_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())

    assert set(fixed_paths) <= names


def test_heteromer_p6_no_hit_omits_only_conditional_solution_assets(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent
    p0_paths = _write_p0_paths(remote_root)
    phenix_manifest = Path(p0_paths.read_text(encoding="ascii").splitlines()[6])
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    p0_paths.unlink()
    _run(
        [
            str(dispatcher),
            "stage",
            HETEROMER_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "heteromer-smoke",
            str(phenix_manifest),
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
    )
    _run(
        [str(dispatcher), "submit", HETEROMER_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    job_environment = dict(environment)
    job_environment.update(
        {
            "FAKE_P6_WRONG_NO_SOLUTION": "1",
            "SLURM_JOB_ID": "123",
            "SLURM_CPUS_PER_TASK": "8",
            "SLURM_TMPDIR": str(tmp_path / "slurm-tmp"),
        }
    )
    _run(
        [str(smoke_job), HETEROMER_RUN_ID, str(remote_root), "heteromer-smoke"],
        cwd=tmp_path,
        environment=job_environment,
    )
    run = remote_root / "runs" / HETEROMER_RUN_ID
    checksum_paths = {
        line.split(maxsplit=1)[1]
        for line in (run / "artifacts/qualification/heteromer-smoke-checksums.sha256")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    wrong_root = "artifacts/heteromer-smoke/p6/wrong-partner"
    assert {
        f"{wrong_root}/partner_search_result.json",
        f"{wrong_root}/partner_search_result.jsonl",
        f"{wrong_root}/phaser_command.json",
        f"{wrong_root}/partner_search.eff",
        f"{wrong_root}/PHASER.log",
        f"{wrong_root}/phenix.phaser.capture.log",
    } <= checksum_paths
    assert f"{wrong_root}/PHASER.1.pdb" not in checksum_paths
    assert f"{wrong_root}/PHASER.1.mtz" not in checksum_paths

    archive = _run(
        [str(dispatcher), "collect", HETEROMER_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as collected:
        names = set(collected.getnames())
    assert f"{wrong_root}/PHASER.log" in names
    assert f"{wrong_root}/partner_search.eff" in names
    assert f"{wrong_root}/PHASER.1.pdb" not in names
    assert f"{wrong_root}/PHASER.1.mtz" not in names


def test_heteromer_stage_rejects_unbound_p6_protocol_provenance(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = dispatcher.parent.parent
    p0_paths = _write_p0_paths(remote_root)
    phenix_manifest = Path(p0_paths.read_text(encoding="ascii").splitlines()[6])
    phenix_sha256 = hashlib.sha256(phenix_manifest.read_bytes()).hexdigest()
    p0_paths.unlink()
    mismatched_environment = dict(environment)
    mismatched_environment["FAKE_P6_PROVENANCE_MISMATCH"] = "1"

    result = _run(
        [
            str(dispatcher),
            "stage",
            HETEROMER_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "heteromer-smoke",
            str(phenix_manifest),
            phenix_sha256,
        ],
        cwd=tmp_path,
        environment=mismatched_environment,
        success=False,
    )

    assert _decode_protocol(result.stdout)["failure_class"] == "software_failure"


def test_p2_diverse_runs_bounded_offline_fanout_and_collects_review_package(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)

    readiness = _decode_protocol(
        _run(
            [str(dispatcher), "readiness", "p2-diverse"],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert readiness["profile"] == "p2-diverse"
    assert readiness["ready"] == "true"
    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                P2_DIVERSE_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "p2-diverse",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "p2-diverse"
    run = remote_root / "runs" / P2_DIVERSE_RUN_ID
    assert (run / "state/p2-diverse-login-stage.sha256").is_file()
    login_log = (run / "logs/p2-diverse-login-stage.log").read_text(encoding="utf-8")
    assert "phase=p2_diverse_login_pdb_search" in login_log
    assert "phase=p2_diverse_login_coordinate_registration" in login_log
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["p2_diverse_login_stage_sha256"]) == 64

    _install_fake_p1_runtime(run)
    submitted = _decode_protocol(
        _run(
            [str(dispatcher), "submit", P2_DIVERSE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert submitted["profile"] == "p2-diverse"
    arguments = (tmp_path / "sbatch-args").read_text(encoding="utf-8").splitlines()
    assert "--time=24:00:00" in arguments
    assert arguments[-4:] == [
        str(smoke_job),
        P2_DIVERSE_RUN_ID,
        str(remote_root),
        "p2-diverse",
    ]

    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "123"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    _run(
        [str(smoke_job), P2_DIVERSE_RUN_ID, str(remote_root), "p2-diverse"],
        cwd=tmp_path,
        environment=job_environment,
    )

    result = json.loads((run / "state/job-result.json").read_text(encoding="utf-8"))
    assert result["failure_class"] == "success"
    assert result["profile"] == "p2-diverse"
    summary = json.loads(
        (run / "artifacts/qualification/p2-diverse-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["registered_mapping_count"] == 1
    assert summary["experimental_model_count"] == 1
    assert summary["hypothesis_count"] == 2
    assert summary["predicted_hypothesis_count"] == 1
    assert summary["experimental_hypothesis_count"] == 1
    assert summary["result_count"] == 2
    assert summary["completed_no_hit_count"] == 2
    assert summary["mr_seed_review_package_id"] == "reviewpkg_" + "a" * 64
    assert len(summary["mr_seed_review_manifest_sha256"]) == 64
    assert (
        summary["login_pdb_search_sha256"] == (summary["scheduled_pdb_search_sha256"])
    )
    resume = json.loads(
        (
            run / "artifacts/qualification/p2-diverse-first-copy-resume-check.json"
        ).read_text(encoding="utf-8")
    )
    assert resume["process_count"] == 3
    assert resume["cached_process_count"] == 3
    commands = (run / "execution/fake-nextflow-commands.log").read_text(
        encoding="utf-8"
    )
    assert "qualification.nf --qualification_stage diverse_first_copy" in commands
    assert "--maximum_first_copy_jobs 25" in commands

    archive_path = tmp_path / "p2-diverse-collected.tar.gz"
    archive_path.write_bytes(
        _run(
            [str(dispatcher), "collect", P2_DIVERSE_RUN_ID, OWNER_ID],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
    assert "artifacts/qualification/p2-diverse-summary.json" in names
    assert "artifacts/qualification/p2-diverse-results.jsonl" in names
    assert "artifacts/qualification/p2-diverse-commands.jsonl" in names
    assert "artifacts/qualification/p2-diverse-log-tails.txt" in names
    assert "artifacts/qualification/p2-diverse-artifact-sha256.tsv" in names
    assert (
        "artifacts/qualification/p2-diverse-review/mr_seed_review_manifest.json"
    ) in names
    assert (
        "artifacts/qualification/p2-diverse-review/mr_seed_candidates.html"
    ) in names
    assert ("artifacts/qualification/p2-diverse-review/approved_mr_seeds.tsv") in names
    assert (
        "artifacts/p2-diverse/first-copy/diverse_first_copy_funnel/mr_hypotheses.jsonl"
    ) in names


def _install_review_asset_fixture(run: Path) -> tuple[str, set[str]]:
    review = run / "artifacts/qualification/p2-diverse-review"
    state = run / "state"
    review.mkdir(parents=True, exist_ok=True)
    state.mkdir(exist_ok=True)
    solution_id = "sol_" + "a" * 64
    package_id = "reviewpkg_" + "b" * 64
    assets = {
        "command": ("phaser_command.json", b'{"command":"phenix.phaser"}\n'),
        "normalised_result": (
            "normalised_mr_result.jsonl",
            b'{"execution_status":"completed_hit","llg":27.0,"tfz":5.5,'
            b'"packing_summary":{"top_solution_packed":true,'
            b'"score_gate_operator":"or",'
            b'"score_gate_llg_strictly_greater_than":50,'
            b'"score_gate_tfz_strictly_greater_than":5,'
            b'"score_gate_passed":true},"placed_copy_count":1,'
            b'"solution_coordinate_path":"PHASER.1.pdb",'
            b'"output_mtz_path":"PHASER.1.mtz"}\n',
        ),
        "output_mtz": ("solution.mtz", b"fake mtz\n"),
        "raw_log": ("phaser.log", b"fake Phaser log\n"),
        "solution_coordinate": ("solution.pdb", b"ATOM\n"),
    }
    review_outputs = {
        "approval_candidates_tsv": ("mr_seed_approval_candidates.tsv", b"item_id\n"),
        "approval_template_tsv": ("approved_mr_seeds.tsv", b"checkpoint\n"),
        "review_html": ("mr_seed_candidates.html", b"<html></html>\n"),
        "review_tsv": ("mr_seed_candidates.tsv", b"solution_id\n"),
    }
    manifest = {
        "schema_version": "1.0",
        "adapter_version": "mr-seed-review-v3",
        "package_id": package_id,
        "numeric_screen_excludes_candidates": False,
        "approval_requires_explicit_human_decision": True,
        "inspectable_solution_count": 1,
        "score_gate": {
            "llg_strictly_greater_than": 50.0,
            "operator": "or",
            "policy_id": "strict_llg_gt_50_or_tfz_gt_5",
            "tfz_strictly_greater_than": 5.0,
        },
        "items": [
            {
                "inspectable_solution": True,
                "solution_id": solution_id,
                "copied_assets": {
                    key: f"assets/{solution_id}/{basename}"
                    for key, (basename, _) in assets.items()
                },
                "copied_asset_sha256": {
                    key: hashlib.sha256(payload).hexdigest()
                    for key, (_, payload) in assets.items()
                },
            }
        ],
        "outputs": {
            key: {
                "path": basename,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for key, (basename, payload) in review_outputs.items()
        },
    }
    manifest_path = review / "mr_seed_review_manifest.json"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    summary_path = run / "artifacts/qualification/p2-diverse-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": run.name,
                "profile": "p2-diverse",
                "completed_hit_count": 1,
                "mr_seed_review_package_id": package_id,
                "mr_seed_review_manifest_sha256": manifest_sha256,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    job_path = state / "job-result.json"
    job_path.write_text(
        json.dumps(
            {
                "run_id": run.name,
                "profile": "p2-diverse",
                "failure_class": "success",
                "scheduler_state": "COMPLETED",
                "exit_code": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    expected = {
        "artifacts/qualification/p2-diverse-review/mr_seed_review_manifest.json",
        "artifacts/qualification/p2-diverse-summary.json",
        "state/job-result.json",
    }
    for basename, payload in assets.values():
        relative = (
            f"artifacts/qualification/p2-diverse-review/assets/{solution_id}/{basename}"
        )
        path = run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        expected.add(relative)
    for basename, payload in review_outputs.values():
        relative = f"artifacts/qualification/p2-diverse-review/{basename}"
        (run / relative).write_bytes(payload)
        expected.add(relative)
    return manifest_sha256, expected


def test_review_collect_streams_all_manifest_inspectable_checksum_assets(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    staged = _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                P2_DIVERSE_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "p2-diverse",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    assert staged["profile"] == "p2-diverse"
    run = remote_root / "runs" / P2_DIVERSE_RUN_ID
    manifest_sha256, expected = _install_review_asset_fixture(run)

    result = _run(
        [
            str(dispatcher),
            "review-collect",
            P2_DIVERSE_RUN_ID,
            OWNER_ID,
            manifest_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
    )

    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
        names = set(archive.getnames())
        assert names == expected
        solution = archive.extractfile(
            next(name for name in names if name.endswith("solution.pdb"))
        )
        assert solution is not None
        assert solution.read() == b"ATOM\n"


def test_review_collect_rejects_manifest_checksum_and_asset_tampering(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _write_p0_paths(remote_root)
    _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                P2_DIVERSE_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "p2-diverse",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    run = remote_root / "runs" / P2_DIVERSE_RUN_ID
    manifest_sha256, _ = _install_review_asset_fixture(run)

    wrong_manifest = _run(
        [
            str(dispatcher),
            "review-collect",
            P2_DIVERSE_RUN_ID,
            OWNER_ID,
            "0" * 64,
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(wrong_manifest.stdout)["failure_class"] == (
        "transfer_failure"
    )

    solution = next(run.rglob("solution.pdb"))
    solution.write_bytes(b"tampered\n")
    tampered = _run(
        [
            str(dispatcher),
            "review-collect",
            P2_DIVERSE_RUN_ID,
            OWNER_ID,
            manifest_sha256,
        ],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(tampered.stdout)["failure_class"] == "transfer_failure"


def _install_t12_review_asset_fixture(
    run: Path,
) -> tuple[str, str, str, set[str]]:
    seed = "sol_" + "a" * 64
    refinement_id = "refine_" + "b" * 64
    assets = {
        "brief_refine_001.pdb": b"ATOM\n",
        "brief_refine_001.mtz": b"MTZ\n",
        "brief_refine_2mFo-DFc.ccp4": b"MAP\n",
        "brief_refine_mFo-DFc.ccp4": b"DIFFERENCE\n",
        "sequence_from_map.pdb": b"MODEL\n",
    }
    digests = {
        name: hashlib.sha256(payload).hexdigest() for name, payload in assets.items()
    }
    qualification = run / "artifacts/qualification"
    state = run / "state"
    qualification.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    summary_path = qualification / "t12-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run.name,
                "profile": "t12",
                "candidate_count": 1,
                "completed_refinement_count": 1,
                "failed_refinement_count": 0,
                "completed_sequence_count": 1,
                "failed_sequence_count": 0,
                "all_candidates_retained": True,
                "all_resume_processes_cached": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    refinement_path = qualification / "t12-refinement-results.jsonl"
    refinement_path.write_text(
        json.dumps(
            {
                "seed_solution_id": seed,
                "refinement_id": refinement_id,
                "execution_status": "completed_success",
                "refined_model_path": "brief_refine_001.pdb",
                "refined_model_sha256": digests["brief_refine_001.pdb"],
                "refined_mtz_path": "brief_refine_001.mtz",
                "refined_mtz_sha256": digests["brief_refine_001.mtz"],
                "map_path": "brief_refine_2mFo-DFc.ccp4",
                "map_sha256": digests["brief_refine_2mFo-DFc.ccp4"],
                "difference_map_path": "brief_refine_mFo-DFc.ccp4",
                "difference_map_sha256": digests["brief_refine_mFo-DFc.ccp4"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sequence_path = qualification / "t12-sequence-results.jsonl"
    sequence_path.write_text(
        json.dumps(
            {
                "seed_solution_id": seed,
                "refinement_id": refinement_id,
                "execution_status": "completed_hit",
                "output_model_path": "sequence_from_map.pdb",
                "output_model_sha256": digests["sequence_from_map.pdb"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (state / "job-result.json").write_text(
        json.dumps(
            {
                "run_id": run.name,
                "profile": "t12",
                "failure_class": "success",
                "scheduler_state": "COMPLETED",
                "exit_code": 0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    expected: set[str] = set()
    for name, payload in assets.items():
        relative = f"artifacts/t12/t12_{seed}/{name}"
        path = run / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        expected.add(relative)
    context_payloads = {
        "sequence_groups.jsonl": b'{"sequence_group_id":"seq_test"}\n',
        "source_records.jsonl": b'{"source_record_id":"src_test"}\n',
        "preflight.jsonl": b'{"preflight_id":"preflight_test"}\n',
    }
    stage_root = run / "artifacts/t12-inputs"
    context_root = stage_root / "inputs"
    context_root.mkdir(parents=True, exist_ok=True)
    for name, payload in context_payloads.items():
        relative = f"artifacts/t12-inputs/inputs/{name}"
        (context_root / name).write_bytes(payload)
        expected.add(relative)
    (stage_root / "t12_stage_manifest.json").write_text(
        json.dumps(
            {
                "seed_count": 1,
                "sequence_groups_sha256": hashlib.sha256(
                    context_payloads["sequence_groups.jsonl"]
                ).hexdigest(),
                "source_records_sha256": hashlib.sha256(
                    context_payloads["source_records.jsonl"]
                ).hexdigest(),
                "preflight_sha256": hashlib.sha256(
                    context_payloads["preflight.jsonl"]
                ).hexdigest(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return (
        hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        hashlib.sha256(refinement_path.read_bytes()).hexdigest(),
        hashlib.sha256(sequence_path.read_bytes()).hexdigest(),
        expected,
    )


def test_t12_review_collect_streams_only_typed_checksum_assets(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    remote_root = smoke_job.parent.parent
    _decode_protocol(
        _run(
            [
                str(dispatcher),
                "stage",
                T12_RUN_ID,
                commit,
                _lock_checksum(tmp_path),
                OWNER_ID,
                "1",
                "t12",
            ],
            cwd=tmp_path,
            environment=environment,
        ).stdout
    )
    run = remote_root / "runs" / T12_RUN_ID
    summary_sha, refinement_sha, sequence_sha, expected = (
        _install_t12_review_asset_fixture(run)
    )

    result = _run(
        [
            str(dispatcher),
            "t12-review-collect",
            T12_RUN_ID,
            OWNER_ID,
            summary_sha,
            refinement_sha,
            sequence_sha,
        ],
        cwd=tmp_path,
        environment=environment,
    )

    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:gz") as archive:
        assert set(archive.getnames()) == expected


def test_p2_diverse_stage_classifies_coordinate_registration_failure(
    tmp_path: Path,
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _write_p0_paths(smoke_job.parent.parent)
    failing_environment = dict(environment)
    failing_environment["FAKE_PDB_REGISTRATION_FAIL"] = "1"

    failed = _run(
        [
            str(dispatcher),
            "stage",
            P2_DIVERSE_RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "p2-diverse",
        ],
        cwd=tmp_path,
        environment=failing_environment,
        success=False,
    )

    assert _decode_protocol(failed.stdout)["failure_class"] == "transfer_failure"
    run = smoke_job.parent.parent / "runs" / P2_DIVERSE_RUN_ID
    assert (run / "state/phase").read_text(encoding="ascii").strip() == ("stage_failed")
    assert (run / "state/failure-class").read_text(
        encoding="ascii"
    ).strip() == "transfer_failure"


def test_remote_dispatcher_classifies_scheduler_rejection_and_concurrency(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    lock_checksum = _lock_checksum(tmp_path)
    for run_id in (RUN_ID, SECOND_RUN_ID):
        _run(
            [
                str(dispatcher),
                "stage",
                run_id,
                commit,
                lock_checksum,
                OWNER_ID,
                "1",
                "smoke",
            ],
            cwd=tmp_path,
            environment=environment,
        )

    rejected_environment = dict(environment)
    rejected_environment["FAKE_SBATCH_REJECT"] = "1"
    rejected = _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=rejected_environment,
        success=False,
    )
    assert _decode_protocol(rejected.stdout)["failure_class"] == ("scheduler_rejection")

    _run(
        [str(dispatcher), "submit", SECOND_RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )
    third_run = "gtd-smoke-20260802T120002Z-0123456789ab-01234569"
    _run(
        [
            str(dispatcher),
            "stage",
            third_run,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    active_environment = dict(environment)
    active_environment["FAKE_SQUEUE_STATE"] = "RUNNING"
    concurrent = _run(
        [str(dispatcher), "submit", third_run, OWNER_ID],
        cwd=tmp_path,
        environment=active_environment,
        success=False,
    )
    assert _decode_protocol(concurrent.stdout)["failure_class"] == (
        "scheduler_rejection"
    )

    fourth_run = "gtd-smoke-20260802T120003Z-0123456789ab-0123456a"
    _run(
        [
            str(dispatcher),
            "stage",
            fourth_run,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    stale_lock_environment = dict(environment)
    stale_lock_environment["FAKE_SQUEUE_FAIL"] = "1"
    recovered = _run(
        [str(dispatcher), "submit", fourth_run, OWNER_ID],
        cwd=tmp_path,
        environment=stale_lock_environment,
    )
    assert _decode_protocol(recovered.stdout)["job_id"] == "123"


def test_remote_dispatcher_classifies_node_failure_and_oversized_collection(
    tmp_path: Path,
) -> None:
    dispatcher, _, environment, commit = _prepare_remote_layout(tmp_path)
    lock_checksum = _lock_checksum(tmp_path)
    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            lock_checksum,
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    _run(
        [str(dispatcher), "submit", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
    )

    node_environment = dict(environment)
    node_environment["FAKE_SACCT_STATE"] = "NODE_FAIL"
    node_status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=node_environment,
    )
    assert _decode_protocol(node_status.stdout)["failure_class"] == "node_failure"

    unavailable_environment = dict(environment)
    unavailable_environment["FAKE_SQUEUE_FAIL"] = "1"
    unavailable_environment["FAKE_SACCT_FAIL"] = "1"
    unavailable_status = _run(
        [str(dispatcher), "status", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=unavailable_environment,
    )
    unavailable_fields = _decode_protocol(unavailable_status.stdout)
    assert unavailable_fields["scheduler_state"] == "UNKNOWN"
    assert unavailable_fields["terminal"] == "false"

    smoke_log = tmp_path / "remote-root" / "runs" / RUN_ID / "logs" / "smoke.log"
    smoke_log.touch()
    os.truncate(smoke_log, 128 * 1024 * 1024 + 1)
    oversized = _run(
        [str(dispatcher), "collect", RUN_ID, OWNER_ID],
        cwd=tmp_path,
        environment=environment,
        success=False,
    )
    assert _decode_protocol(oversized.stdout)["failure_class"] == "transfer_failure"


@pytest.mark.parametrize(
    ("environment_key", "expected_class"),
    [
        ("FAKE_PIXI_INSTALL_FAIL", "environment_failure"),
        ("FAKE_PIXI_RUN_FAIL", "test_failure"),
    ],
)
def test_smoke_job_distinguishes_environment_and_test_failures(
    tmp_path: Path, environment_key: str, expected_class: str
) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "456"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment[environment_key] = "1"
    _run(
        [str(smoke_job), RUN_ID, str(smoke_job.parent.parent), "smoke"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )
    failure = (
        tmp_path / "remote-root" / "runs" / RUN_ID / "state" / "failure-class"
    ).read_text(encoding="utf-8")
    assert failure.strip() == expected_class


def test_smoke_job_records_term_signal_as_cancellation(tmp_path: Path) -> None:
    dispatcher, smoke_job, environment, commit = _prepare_remote_layout(tmp_path)
    _run(
        [
            str(dispatcher),
            "stage",
            RUN_ID,
            commit,
            _lock_checksum(tmp_path),
            OWNER_ID,
            "1",
            "smoke",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    job_environment = dict(environment)
    job_environment["SLURM_JOB_ID"] = "789"
    job_environment["SLURM_TMPDIR"] = str(tmp_path / "slurm-tmp")
    job_environment["FAKE_PIXI_TERM_PARENT"] = "1"
    terminated = _run(
        [str(smoke_job), RUN_ID, str(smoke_job.parent.parent), "smoke"],
        cwd=tmp_path,
        environment=job_environment,
        success=False,
    )
    assert terminated.returncode == 143
    result_path = (
        tmp_path / "remote-root" / "runs" / RUN_ID / "state" / "job-result.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["scheduler_state"] == "CANCELLED"
    assert result["failure_class"] == "unknown_failure"
    assert result["exit_code"] == 143
    scratch = job_environment["SLURM_TMPDIR"] + f"/nf-gtd-789-{RUN_ID}"
    assert not Path(scratch).exists()
