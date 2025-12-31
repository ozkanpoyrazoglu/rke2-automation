#!/bin/bash
#
# Local secrets scanning using Gitleaks in Docker
# Usage: ./scripts/scan-secrets.sh
#

set -e

echo "🔍 Scanning repository for secrets using Gitleaks..."
echo ""

# Run gitleaks in Docker (no installation needed)
docker run --rm -v "$(pwd):/repo" \
  zricethezav/gitleaks:latest \
  detect \
  --source=/repo \
  --config=/repo/.gitleaks.toml \
  --verbose \
  --no-banner

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ No secrets detected! Safe to push."
else
    echo ""
    echo "❌ Secrets detected! Review the findings above."
    exit 1
fi
