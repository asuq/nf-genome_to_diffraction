#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: prepare_project_layout.sh --root ABSOLUTE_PATH [--dry-run]' \
        '' \
        'Create the recommended runtime directory layout:' \
        '' \
        '  ROOT/' \
        '  |-- input/' \
        '  |   |-- genome/' \
        '  |   `-- diffraction/' \
        '  |-- manifests/' \
        '  |-- software/manifests/' \
        '  |-- databases/' \
        '  |-- cache/' \
        '  |   |-- nextflow-home/' \
        '  |   `-- work/' \
        '  |-- logs/' \
        '  `-- results/' \
        '' \
        'The operation is idempotent and does not remove or overwrite files.'
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}

project_root=''
dry_run=false

while (($# > 0)); do
    case "$1" in
        --root)
            (($# >= 2)) || fail '--root requires an absolute path'
            project_root=$2
            shift 2
            ;;
        --dry-run)
            dry_run=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "$project_root" ]] || fail '--root is required'
[[ "$project_root" == /* ]] || fail '--root must be an absolute path'
[[ "$project_root" != / ]] || fail 'refusing to use the filesystem root'
case "$project_root" in
    */../*|*/..|*/./*|*/.) fail '--root must not contain dot path components' ;;
esac

directories=(
    'input/genome'
    'input/diffraction'
    'manifests'
    'software/manifests'
    'databases'
    'cache/nextflow-home'
    'cache/work'
    'logs'
    'results'
)

for relative_path in "${directories[@]}"; do
    destination="${project_root}/${relative_path}"
    if "$dry_run"; then
        printf '[prepare:dry-run] mkdir -p %s\n' "$destination"
    else
        mkdir -p "$destination"
        printf '[prepare] ready %s\n' "$destination"
    fi
done

printf '[prepare] project root: %s\n' "$project_root"
