#!/usr/bin/env bash
if [ ! -e $(basename $0) ]; then
  echo "Run this script from the directory in which the script lives for best results"
  exit
fi
docker exec -it ig-web bash -c "mkdir -p /opt/static/icosa-sketch-assets/" && \
docker exec -it ig-web bash -c "mkdir -p /opt/static/icosa-sketch-assets-experimental/" && \
docker exec -it ig-web bash -c "mkdir -p /opt/static/icosa-sketch-assets-previous/"

CDIR="$(pwd)"
DIR="../icosa-sketch-assets"

if [ ! -d "$DIR" -a ! -e "$DIR" ]; then
  git clone https://github.com/icosa-foundation/icosa-sketch-assets "$DIR"
fi

cd "$DIR"
git checkout main && \
git pull && \
docker cp brushes ig-web:/opt/static/icosa-sketch-assets/brushes && \
docker cp textures ig-web:/opt/static/icosa-sketch-assets/textures && \
docker cp environments ig-web:/opt/static/icosa-sketch-assets/environments && \
git checkout versions/previous && \
git pull && \
docker cp brushes/. ig-web:/opt/static/icosa-sketch-assets-previous/brushes/ && \
docker cp textures/. ig-web:/opt/static/icosa-sketch-assets-previous/textures/ && \
docker cp environments/. ig-web:/opt/static/icosa-sketch-assets-previous/environments/ && \
git checkout versions/experimental && \
git pull && \
docker cp brushes/. ig-web:/opt/static/icosa-sketch-assets-experimental/brushes/ && \
docker cp textures/. ig-web:/opt/static/icosa-sketch-assets-experimental/textures/ && \
docker cp environments/. ig-web:/opt/static/icosa-sketch-assets-experimental/environments/

cd "$CDIR"
