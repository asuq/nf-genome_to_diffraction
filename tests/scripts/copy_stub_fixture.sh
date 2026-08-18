#!/usr/bin/env bash
# Copy one test fixture tree without retaining source write restrictions.

set -euo pipefail

if [[ "$#" -ne 2 ]]; then
    printf 'usage: copy_stub_fixture.sh SOURCE_DIRECTORY OUTPUT_DIRECTORY\n' >&2
    exit 2
fi

source_directory="$1"
output_directory="$2"

[[ -d "$source_directory" && ! -L "$source_directory" ]] || {
    printf 'stub fixture source must be a directory, not a symbolic link\n' >&2
    exit 2
}
[[ ! -e "$output_directory" && ! -L "$output_directory" ]] || {
    printf 'stub fixture output already exists\n' >&2
    exit 2
}

repair_output_permissions() {
    [[ ! -e "$output_directory" ]] || \
        chmod -R u+rwX "$output_directory" 2>/dev/null || true
}

trap repair_output_permissions EXIT
mkdir "$output_directory"
cp -R "$source_directory/." "$output_directory/"
chmod -R u+rwX "$output_directory"
trap - EXIT
