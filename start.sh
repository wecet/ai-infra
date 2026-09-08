#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
profile="${1:-dev}"
echo "Starting AI Infrastructure with profile: $profile"
"$project_root/scripts/compose.sh" "$profile" pull --ignore-buildable
"$project_root/scripts/compose.sh" "$profile" up -d --build
"$project_root/scripts/compose.sh" "$profile" ps
