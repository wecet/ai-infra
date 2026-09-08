#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
profile="${1:-dev}"
if (($#)); then shift; fi
if [[ ! "$profile" =~ ^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*$ ]]; then
  echo "Invalid profile name: $profile" >&2
  exit 2
fi
profile_file="$project_root/profiles/$profile.env"
if [[ ! -f "$profile_file" ]]; then
  echo "Profile does not exist: $profile_file" >&2
  exit 2
fi
if [[ "$profile" != dev && "$profile" != *.dev && "$profile" != *.nolock ]]; then
  echo "Compose requires a plaintext dev or *.nolock profile; use Deployment Manager for encrypted profiles." >&2
  exit 2
fi
exec docker compose --project-directory "$project_root" --env-file "$profile_file" -f "$project_root/docker-compose.yaml" "$@"
