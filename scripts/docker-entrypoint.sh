#!/bin/sh
# TeamScout container entrypoint (Docker Compose + Fly.io).
# - Co-locates uploads on the /data volume next to SQLite when possible
# - Optionally restores/replicates SQLite via Litestream when LITESTREAM_S3_BUCKET is set
# - Drops privileges to appuser (uid 1000) when started as root
set -eu

mkdir -p /data/uploads

# App code writes to /app/uploads.
# Fly: only /data is mounted → replace image dir with symlink to /data/uploads.
# Compose: may mount a separate volume on /app/uploads → leave that mount alone.
if [ -L /app/uploads ]; then
  :
elif [ -d /app/uploads ]; then
  if rmdir /app/uploads 2>/dev/null; then
    ln -s /data/uploads /app/uploads
  else
    # Non-empty or volume mountpoint — keep directory (compose teamscout-uploads)
    echo "entrypoint: keeping existing /app/uploads (volume mount or non-empty)"
  fi
else
  ln -s /data/uploads /app/uploads
fi

if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appuser /data 2>/dev/null || true
  chown -R appuser:appuser /app/uploads 2>/dev/null || true
fi

run_as_app() {
  if [ "$(id -u)" = "0" ] && command -v runuser >/dev/null 2>&1; then
    exec runuser -u appuser -- "$@"
  fi
  exec "$@"
}

DB_PATH="${LITESTREAM_DB_PATH:-/data/teamscout.db}"
LITESTREAM_CONFIG="${LITESTREAM_CONFIG:-/tmp/litestream.runtime.yml}"

# Map LITESTREAM_* credentials onto AWS_* when set so Litestream's default
# credential chain works without writing empty access-key fields into YAML.
if [ -n "${LITESTREAM_ACCESS_KEY_ID:-}" ]; then
  export AWS_ACCESS_KEY_ID="$LITESTREAM_ACCESS_KEY_ID"
fi
if [ -n "${LITESTREAM_SECRET_ACCESS_KEY:-}" ]; then
  export AWS_SECRET_ACCESS_KEY="$LITESTREAM_SECRET_ACCESS_KEY"
fi

write_litestream_config() {
  # Omit empty optional keys (endpoint). Never emit access-key-id/secret as ""
  # — empty static keys would block the AWS SDK ambient chain.
  {
    echo "dbs:"
    echo "  - path: ${DB_PATH}"
    echo "    replicas:"
    echo "      - type: s3"
    echo "        bucket: ${LITESTREAM_S3_BUCKET}"
    echo "        path: teamscout"
    if [ -n "${LITESTREAM_S3_REGION:-}" ]; then
      echo "        region: ${LITESTREAM_S3_REGION}"
    fi
    if [ -n "${LITESTREAM_S3_ENDPOINT:-}" ]; then
      echo "        endpoint: ${LITESTREAM_S3_ENDPOINT}"
    fi
  } > "$LITESTREAM_CONFIG"
  chmod 644 "$LITESTREAM_CONFIG"
}

if [ -n "${LITESTREAM_S3_BUCKET:-}" ] && command -v litestream >/dev/null 2>&1; then
  if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "entrypoint: ERROR Litestream enabled (LITESTREAM_S3_BUCKET set) but credentials missing." >&2
    echo "entrypoint: set LITESTREAM_ACCESS_KEY_ID+LITESTREAM_SECRET_ACCESS_KEY or AWS_ACCESS_KEY_ID+AWS_SECRET_ACCESS_KEY" >&2
    exit 1
  fi
  write_litestream_config
  if [ ! -f "$DB_PATH" ]; then
    echo "entrypoint: litestream restore (if replica exists) -> $DB_PATH"
    # -if-replica-exists: exit 0 when no replica yet (first deploy).
    # Any other failure (bad creds, network, config) is non-zero → refuse start
    # so we do not replicate a fresh empty DB over operator expectations.
    if [ "$(id -u)" = "0" ] && command -v runuser >/dev/null 2>&1; then
      if ! runuser -u appuser -- litestream restore -if-replica-exists -config "$LITESTREAM_CONFIG" "$DB_PATH"; then
        echo "entrypoint: ERROR litestream restore failed. Fix replica access or unset LITESTREAM_S3_BUCKET for volume-only." >&2
        exit 1
      fi
    else
      if ! litestream restore -if-replica-exists -config "$LITESTREAM_CONFIG" "$DB_PATH"; then
        echo "entrypoint: ERROR litestream restore failed. Fix replica access or unset LITESTREAM_S3_BUCKET for volume-only." >&2
        exit 1
      fi
    fi
  fi
  echo "entrypoint: litestream replicate enabled (LITESTREAM_S3_BUCKET set)"
  if [ "$#" -gt 0 ]; then
    CMD="$*"
  else
    CMD="uvicorn app.main:app --host 0.0.0.0 --port 8000"
  fi
  run_as_app litestream replicate -config "$LITESTREAM_CONFIG" -exec "$CMD"
fi

if [ "$#" -gt 0 ]; then
  run_as_app "$@"
else
  run_as_app uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
