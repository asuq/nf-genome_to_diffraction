#!/usr/bin/env bash
set -euo pipefail

# This administrative wrapper never downloads Phenix. Run it inside the Pixi
# environment and pass a user-supplied installer plus its full SHA-256.
exec genome-to-diffraction phenix install "$@"
