#!/usr/bin/env bash
# Run the installed Clinica environment with the separately built dcm2niix.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
converter_dir="$(dirname -- "$repo_dir")/dcm2niix/build/bin"
if [[ ! -x "$repo_dir/.venv-clinica/bin/clinica" || ! -x "$converter_dir/dcm2niix" ]]; then
  printf '%s\n' "Clinica environment or dcm2niix build is missing; see local_mac/README.md." >&2
  exit 1
fi
export PATH="$converter_dir:$PATH"
exec "$repo_dir/.venv-clinica/bin/clinica" "$@"
