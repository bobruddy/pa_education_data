#!/bin/sh
# Start the data container on docker09, or replace it.
# Usage: scripts/docker09-data.sh <git sha>
#
# NFS is mounted at /var/pde inside the container. That container is the only
# writer. It serves refined/<table>.parquet on port 8091, not 8090.
# docker09 must have /etc/pde-data-nfs with one line: host:/export
set -eu
tag=${1:?usage: scripts/docker09-data.sh <git sha>}
image="192.168.150.59:443/pde-data:${tag}"
ssh docker09 sh -s "$image" <<'EOF'
set -eu
image=$1
spec=$(tr -d '[:space:]' < /etc/pde-data-nfs)
host=${spec%%:*}
export_path=${spec#*:}
if [ -z "$host" ] || [ -z "$export_path" ] || [ "$host" = "$spec" ]; then
  echo "expected /etc/pde-data-nfs to contain host:/export" >&2
  exit 2
fi
docker pull "$image"
if ! docker volume inspect pde-nfs >/dev/null 2>&1; then
  docker volume create --driver local \
    --opt type=nfs \
    --opt o=addr=${host},rw,nolock \
    --opt device=:${export_path} \
    pde-nfs >/dev/null
fi
if docker inspect pde-data >/dev/null 2>&1; then
  docker rm -f pde-data >/dev/null
fi
docker run -d --name pde-data --restart unless-stopped \
  -p 8091:8091 \
  -e PDE_ROOT=/app \
  -e PDE_DATA=/var/pde \
  -e PDE_DATA_PORT=8091 \
  -v pde-nfs:/var/pde \
  "$image"
EOF
echo "http://192.168.10.116:8091/refined/  ${image}"
