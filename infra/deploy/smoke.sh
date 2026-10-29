#!/usr/bin/env bash
# Smoke test pasca-deploy (S19, Spec §18.4 CI host routing/security headers/CORS).
#   SITE_HOST=... APP_HOST=... ADMIN_HOST=... API_HOST=... PORT=8443 HTTP_PORT=8080 INSECURE=1 infra/deploy/smoke.sh
# INSECURE=1 hanya untuk CA internal lokal (curl -k). Staging publik: jalankan tanpa INSECURE.
set -uo pipefail
SITE_HOST="${SITE_HOST:-umrovia.localhost}"
APP_HOST="${APP_HOST:-app.umrovia.localhost}"; ADMIN_HOST="${ADMIN_HOST:-admin.umrovia.localhost}"; API_HOST="${API_HOST:-api.umrovia.localhost}"
PORT="${PORT:-8443}"; HTTP_PORT="${HTTP_PORT:-8080}"; SUFFIX=$([ "$PORT" = 443 ] && echo "" || echo ":$PORT")
CURL=(curl -s --max-time 20 --resolve "$SITE_HOST:$PORT:127.0.0.1" --resolve "www.$SITE_HOST:$PORT:127.0.0.1" --resolve "$APP_HOST:$PORT:127.0.0.1" --resolve "$ADMIN_HOST:$PORT:127.0.0.1" --resolve "$API_HOST:$PORT:127.0.0.1" --resolve "$API_HOST:$HTTP_PORT:127.0.0.1")
[ "${INSECURE:-0}" = "1" ] && CURL+=(-k)
[ "${RESOLVE_LOCAL:-1}" = "1" ] || CURL=(curl -s --max-time 20 $([ "${INSECURE:-0}" = "1" ] && echo -k))
PASS=0; FAIL=0
check() { if eval "$2"; then echo "OK    $1"; PASS=$((PASS+1)); else echo "GAGAL $1"; FAIL=$((FAIL+1)); fi; }

SITE="https://$SITE_HOST$SUFFIX"; API="https://$API_HOST$SUFFIX"; APP="https://$APP_HOST$SUFFIX"; ADMIN="https://$ADMIN_HOST$SUFFIX"
health=$("${CURL[@]}" "$API/api/v1/health/")
check "API health 200 + database ok" '[[ "$health" == *"\"database\": \"ok\""* || "$health" == *"\"database\":\"ok\""* ]]'
headers=$("${CURL[@]}" -D - -o /dev/null "$API/api/v1/health/")
check "API header nosniff" 'grep -qi "^x-content-type-options: nosniff" <<<"$headers"'
check "API header X-Frame-Options DENY" 'grep -qi "^x-frame-options: DENY" <<<"$headers"'
check "API tidak membocorkan header Server" '! grep -qi "^server:" <<<"$headers"'
check "HTTP dialihkan ke HTTPS" '[[ $("${CURL[@]}" -o /dev/null -w "%{http_code}" "http://$API_HOST:$HTTP_PORT/api/v1/health/") =~ ^30[178]$ ]]'
check "Host tak dikenal ditolak (421/400)" '[[ $("${CURL[@]}" -o /dev/null -w "%{http_code}" -H "Host: evil.example" "$API/api/v1/health/") =~ ^(421|400)$ ]]'
check "Host tak dikenal tanpa sertifikat (TLS ditolak)" '[ "$(curl -sk --max-time 10 -o /dev/null -w "%{http_code}" "https://127.0.0.1:$PORT/api/v1/health/")" = 000 ]'
check "CORS: origin app diizinkan" '"${CURL[@]}" -D - -o /dev/null -X OPTIONS -H "Origin: $APP" -H "Access-Control-Request-Method: GET" "$API/api/v1/me" | grep -qi "^access-control-allow-origin: $APP"'
check "CORS: origin asing ditolak" '! "${CURL[@]}" -D - -o /dev/null -X OPTIONS -H "Origin: https://evil.example" -H "Access-Control-Request-Method: GET" "$API/api/v1/me" | grep -qi "^access-control-allow-origin"'
check "Cookie CSRF Secure" '"${CURL[@]}" -D - -o /dev/null "$API/api/v1/auth/csrf" | grep -i "^set-cookie: csrftoken" | grep -qi "secure"'
check "Halaman login app 200" '[ "$("${CURL[@]}" -o /dev/null -w "%{http_code}" "$APP/login")" = 200 ]'
check "Header keamanan app (X-Frame-Options)" '"${CURL[@]}" -D - -o /dev/null "$APP/login" | grep -qi "^x-frame-options: DENY"'
check "Situs marketing (domain utama) 200" '[ "$("${CURL[@]}" -o /dev/null -w "%{http_code}" "$SITE/")" = 200 ]'
check "Gambar marketing dilayani domain utama" '[ "$("${CURL[@]}" -o /dev/null -w "%{http_code} %{content_type}" "$SITE/marketing/ringkasan.webp")" = "200 image/webp" ]'
check "www → domain utama" '"${CURL[@]}" -D - -o /dev/null "https://www.$SITE_HOST$SUFFIX/pricing" | grep -qi "^location: $SITE/pricing"'
check "Rute aplikasi di domain utama → host app" '"${CURL[@]}" -D - -o /dev/null "$SITE/login" | grep -qi "^location: $APP/login"'
check "Host app / → /login, marketing → domain utama" '"${CURL[@]}" -D - -o /dev/null "$APP/" | grep -qi "^location: /login" && "${CURL[@]}" -D - -o /dev/null "$APP/pricing" | grep -qi "^location: $SITE/pricing"'
check "CORS: origin situs marketing diizinkan" '"${CURL[@]}" -D - -o /dev/null -X OPTIONS -H "Origin: $SITE" -H "Access-Control-Request-Method: POST" "$API/api/v1/contact" | grep -qi "^access-control-allow-origin: $SITE"'
check "Host admin → /platform" '"${CURL[@]}" -D - -o /dev/null "$ADMIN/" | grep -qi "^location: /platform"'
check "Konsol platform tanpa sesi ditolak (API)" '[ "$("${CURL[@]}" -o /dev/null -w "%{http_code}" "$API/api/v1/platform/overview")" = 403 ]'
check "Data tenant tanpa sesi ditolak" '[[ $("${CURL[@]}" -o /dev/null -w "%{http_code}" "$API/api/v1/bookings") =~ ^40[13]$ ]]'
echo "smoke: $PASS lulus, $FAIL gagal"
[ "$FAIL" = 0 ]
