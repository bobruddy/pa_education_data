#!/bin/bash
# Copy data/refined and data/pde.db onto the Jenkins agent.
# Those files are not in git. A push republishes whatever is already there.
# Laptop SSH to cicd times out on VLAN 157, so this enters CT 136 from prox02.
set -euo pipefail
cd "$(dirname "$0")/.."
test -f data/refined/lea.parquet
test -f data/pde.db
remote=(ssh -o ConnectTimeout=20 -J mimas root@192.168.10.202)
"${remote[@]}" 'pct exec 136 -- mkdir -p /var/lib/jenkins/pde-data'
tar -C data -cf - refined pde.db | "${remote[@]}" 'pct exec 136 -- tar -C /var/lib/jenkins/pde-data -xf -'
"${remote[@]}" 'pct exec 136 -- chown -R jenkins:jenkins /var/lib/jenkins/pde-data'
"${remote[@]}" 'pct exec 136 -- du -sh /var/lib/jenkins/pde-data /var/lib/jenkins/pde-data/pde.db /var/lib/jenkins/pde-data/refined'
