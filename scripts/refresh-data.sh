#!/bin/sh
# Run refine, personnel, and check inside the pde-data container on docker09.
# Warm caches skip Excel; new PDE files are downloaded and appended.
# Usage: scripts/refresh-data.sh
set -eu

ssh docker09 'set -eu
  ready=0
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if docker exec pde-data python -c "import pa_edu.refine"; then
      ready=1
      break
    fi
    sleep 2
  done
  test "$ready" = 1
  docker exec pde-data python -m pa_edu.refine
  docker exec pde-data python -m pa_edu.personnel
  docker exec pde-data python -m pa_edu.check
'
echo "data refresh finished"
