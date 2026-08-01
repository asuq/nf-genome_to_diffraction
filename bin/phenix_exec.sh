#!/usr/bin/env bash
set -euo pipefail

# The Python boundary validates the manifest and environment checksum, then opens
# a clean child shell that sources phenix_env.sh and execs this exact argument array.
exec genome-to-diffraction phenix exec "$@"
