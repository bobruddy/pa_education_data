#!/bin/sh
# Start the data container on docker09, or replace it.
# Usage: scripts/docker09-data.sh <git sha>
#
# NFS is blackhole:/mnt/tank04/pde_data, mounted at /var/pde inside the
# container. That container is the only writer. It serves refined parquet
# and a status page on port 8091, not 8090.
set -eu
tag=${1:?usage: scripts/docker09-data.sh <git sha>}
image="192.168.150.59:443/pde-data:${tag}"
nfs_host=blackhole
nfs_path=/mnt/tank04/pde_data
ssh docker09 sh -s "$image" "$nfs_host" "$nfs_path" "$tag" <<'EOF'
set -eu
image=$1
host=$2
export_path=$3
sha=$4
repo=${image%:*}
docker images "$repo" --format '{{.ID}}' | sort -u | while read -r id; do
  if [ -z "$(docker ps -aq --filter ancestor="$id")" ]; then
    docker rmi "$id" >/dev/null 2>&1 || true
  fi
done
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
# The bridge has no IPv6 route. www.pa.gov publishes an AAAA record, and
# a connect to it returns ENETUNREACH. Keep the download on IPv4.
docker run -d --name pde-data --restart unless-stopped \
  --sysctl net.ipv6.conf.all.disable_ipv6=1 \
  -p 8091:8091 \
  -e PDE_ROOT=/app \
  -e PDE_DATA=/var/pde \
  -e PDE_DATA_PORT=8091 \
  -e PDE_GIT_SHA="$sha" \
  -v pde-nfs:/var/pde \
  "$image"
EOF
echo "http://192.168.10.116:8091/  ${image}"
echo "http://192.168.10.116:8091/refined/  ${image}"
