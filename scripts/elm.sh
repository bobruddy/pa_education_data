#!/bin/sh
# Install one pdenumbers tag on elm. Does not build.
# Usage: scripts/elm.sh [latest | <40-character git sha>]
# latest is the newest image the education job pushed. A sha installs that build.
set -eu
tag=${1:-latest}
case $tag in
    latest) ;;
    *)
        if ! printf '%s' "$tag" | grep -Eq '^[0-9a-f]{40}$'; then
            echo "usage: scripts/elm.sh [latest | <40-character git sha>]" >&2
            exit 2
        fi
        ;;
esac
ssh elm "printf 'PDENUMBERS_TAG=%s\n' '$tag' | sudo tee /data/pdenumbers/.env >/dev/null"
ssh elm 'cd /data/pdenumbers && sudo docker compose pull && sudo docker compose up -d'
ssh elm 'sudo docker inspect -f "{{.Config.Image}}" pdenumbers'
