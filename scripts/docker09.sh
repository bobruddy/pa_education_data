#!/bin/sh
# Start the pdenumbers image on docker09, or replace the running container.
# Usage: scripts/docker09.sh <git sha>
# The sha is the Jenkins image tag: 192.168.150.59:443/pdenumbers:<sha>
set -eu
tag=${1:?usage: scripts/docker09.sh <git sha>}
image="192.168.150.59:443/pdenumbers:${tag}"
port=8090
ssh docker09 "set -eu
docker pull '$image'
if docker inspect pdenumbers >/dev/null 2>&1; then
  docker rm -f pdenumbers >/dev/null
fi
docker run -d --name pdenumbers --restart unless-stopped -p ${port}:80 '$image'
"
echo "http://192.168.10.116:${port}/  ${image}"
