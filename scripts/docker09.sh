#!/bin/sh
# Start the pdenumbers image on docker09, or replace the running container.
# Usage: scripts/docker09.sh <git sha>
# The sha is the Jenkins image tag: 192.168.150.59:443/pdenumbers:<sha>
set -eu
tag=${1:?usage: scripts/docker09.sh <git sha>}
image="192.168.150.59:443/pdenumbers:${tag}"
port=8090
# docker09's root is a 64G dataset. Each tag keeps its own html layer, so
# drop copies no container is using before the pull.
ssh docker09 sh -s "$image" "$port" <<'EOF'
set -eu
image=$1
port=$2
repo=${image%:*}
docker images "$repo" --format '{{.ID}}' | sort -u | while read -r id; do
  if [ -z "$(docker ps -aq --filter ancestor="$id")" ]; then
    docker rmi "$id" >/dev/null 2>&1 || true
  fi
done
docker pull "$image"
if docker inspect pdenumbers >/dev/null 2>&1; then
  docker rm -f pdenumbers >/dev/null
fi
docker run -d --name pdenumbers --restart unless-stopped -p "${port}:80" "$image"
EOF
echo "http://192.168.10.116:${port}/  ${image}"
