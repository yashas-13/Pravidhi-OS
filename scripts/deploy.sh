#!/usr/bin/env bash
set -euo pipefail
python3 -m compileall engine gateway cron memory research router_agent
echo "Pravidhi OS source validation complete."
