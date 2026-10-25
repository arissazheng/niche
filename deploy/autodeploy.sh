#!/usr/bin/env bash
# Runs on the server (niche-autodeploy.timer, every 2 minutes): when origin/main has moved,
# builds it beside the running copy, then swaps it in and restarts. A failed build leaves the
# live site as it was. `autodeploy.sh --force` redeploys the current main regardless.
set -euo pipefail
exec 9>/run/niche-deploy.lock
flock -n 9 || exit 0
ROOT=/opt/niche
REPO=$ROOT/repo
[ -d $REPO/.git ] || git clone -q https://github.com/arissazheng/niche.git $REPO
git -C $REPO fetch -q origin main
NEW=$(git -C $REPO rev-parse origin/main)
OLD=$(cat $ROOT/deployed-sha 2>/dev/null || true)
[ "$NEW" = "$OLD" ] && [ "${1:-}" != --force ] && exit 0
echo "Deploying $NEW"

NEXT=$ROOT/src.new
rm -rf $NEXT && mkdir -p $NEXT
git -C $REPO archive "$NEW" backend web | tar -x -C $NEXT
if git -C $REPO cat-file -e "$NEW:deploy/Caddyfile" 2>/dev/null; then
  git -C $REPO archive "$NEW" deploy | tar -x -C $NEXT
else
  cp -r $ROOT/deploy $NEXT/deploy
fi
cp $ROOT/backend/.env $NEXT/backend/.env && chmod 600 $NEXT/backend/.env
ln -s $ROOT/data $NEXT/backend/data
cp $NEXT/deploy/web.env.production $NEXT/web/.env.production
chown -R niche:niche $NEXT
sudo -u niche bash -c "cd $NEXT/web && npm ci --no-audit --no-fund --loglevel=error && npm run build"
[ -d $ROOT/venv ] || python3 -m venv $ROOT/venv
$ROOT/venv/bin/pip install -q "$NEXT/backend[moss]"

rm -rf $ROOT/old && mkdir $ROOT/old
mv $ROOT/backend $ROOT/web $ROOT/deploy $ROOT/old/
mv $NEXT/backend $NEXT/web $NEXT/deploy $ROOT/ && rm -rf $NEXT
cp $ROOT/deploy/niche-api.service $ROOT/deploy/niche-web.service \
   $ROOT/deploy/niche-autodeploy.service $ROOT/deploy/niche-autodeploy.timer /etc/systemd/system/
cp $ROOT/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl restart niche-api niche-web
systemctl reload caddy
echo "$NEW" > $ROOT/deployed-sha
rm -rf $ROOT/old
echo "Deployed $NEW"
