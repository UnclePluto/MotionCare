#!/usr/bin/env sh
set -eu

umask 077
cd "$(dirname "$0")"

ACR_IMAGE=$(sed -n 's/^ACR_IMAGE=//p' .env | head -n 1)
APP_VERSION=$(sed -n 's/^APP_VERSION=//p' .env | head -n 1)
CERTBOT_IMAGE="certbot/certbot@sha256:6bb19cff0b3972a69855686e0ccbd20b98dbfae2aa43845a5df48947ba1401b4"
CERT_NAME="motioncare-whestsun"
ACME_CONTAINER="motioncare-acme"

test -n "$ACR_IMAGE"
test -n "$APP_VERSION"

mkdir -p acme letsencrypt
chown 10001:10001 acme
chmod 755 acme

cleanup() {
  docker rm -f "$ACME_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM
cleanup

docker run -d --name "$ACME_CONTAINER" \
  --network whest_Lan --network-alias motioncare-acme \
  --user 10001:10001 \
  -v "$PWD/acme:/srv:ro" \
  "$ACR_IMAGE:backend-$APP_VERSION" \
  python -m http.server 8080 --directory /srv >/dev/null

if [ "${1:-renew}" = "issue" ]; then
  docker run --rm \
    -v "$PWD/acme:/var/www/certbot" \
    -v "$PWD/letsencrypt:/etc/letsencrypt" \
    "$CERTBOT_IMAGE" certonly \
    --webroot -w /var/www/certbot \
    --cert-name "$CERT_NAME" \
    --non-interactive --agree-tos --register-unsafely-without-email \
    -d mcare.whestsun.com \
    -d mcare-api.whestsun.com \
    -d mcare-wx.whestsun.com
else
  docker run --rm \
    -v "$PWD/acme:/var/www/certbot" \
    -v "$PWD/letsencrypt:/etc/letsencrypt" \
    "$CERTBOT_IMAGE" renew \
    --cert-name "$CERT_NAME" \
    --webroot -w /var/www/certbot \
    --non-interactive --no-random-sleep-on-renew
fi

cert_dir="$PWD/letsencrypt/live/$CERT_NAME"
target_dir="/opt/service/openresty_ssl_conf.d/motioncare-cert"
install -d -m 750 "$target_dir"
install -m 644 "$cert_dir/fullchain.pem" "$target_dir/fullchain.pem"
install -m 600 "$cert_dir/privkey.pem" "$target_dir/privkey.pem"

docker exec OpenResty nginx -t
docker exec OpenResty nginx -s reload
