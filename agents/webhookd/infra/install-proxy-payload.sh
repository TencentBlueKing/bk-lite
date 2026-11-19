# Appended to the generated installer after INSTALL_PATH and ARCHIVE.
parent=$(dirname "$INSTALL_PATH")
name=$(basename "$INSTALL_PATH")
mkdir -p "$parent"
exec 9>"$parent/.$name.install.lock"
flock -n 9 || { echo "Another Proxy installation is in progress" >&2; exit 1; }

stage=$(mktemp -d "$parent/.$name.stage.XXXXXX")
backup=
promoted=false
cleanup() {
    local result=$?
    if [ "$result" -ne 0 ] && $promoted; then
        mkdir -p "$stage"
        if [ -n "$backup" ]; then
            if [ ! -f "$backup/previous/docker-compose.yaml" ]; then
                (cd "$INSTALL_PATH" && docker compose down) || echo "Failed to stop the incomplete Proxy" >&2
            fi
            mv -- "$INSTALL_PATH" "$stage/failed"
            mv -- "$backup/previous" "$INSTALL_PATH"
            if [ -f "$INSTALL_PATH/docker-compose.yaml" ] && ! (cd "$INSTALL_PATH" && docker compose up -d --force-recreate); then
                echo "Proxy rollback restart failed. Check the restored installation." >&2
            fi
        else
            (cd "$INSTALL_PATH" && docker compose down) || echo "Failed to stop the incomplete Proxy" >&2
            mv -- "$INSTALL_PATH" "$stage/failed"
        fi
    elif [ "$result" -ne 0 ] && [ -n "$backup" ] && [ -d "$backup/previous" ]; then
        mv -- "$backup/previous" "$INSTALL_PATH"
        printf 'Failed Proxy files retained in %s\n' "$stage/failed" >&2
    else
        rm -rf -- "$stage"
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -e "$INSTALL_PATH" ] || [ -L "$INSTALL_PATH" ]; then
    if [ ! -d "$INSTALL_PATH" ] || [ -L "$INSTALL_PATH" ]; then
        echo "Proxy install path must be a regular directory" >&2
        exit 1
    fi
    if [ -n "$(find "$INSTALL_PATH" -type l -print -quit)" ]; then
        echo "Proxy install directory contains a symbolic link. Review the upgrade manually." >&2
        exit 1
    fi
    cp -a -- "$INSTALL_PATH"/. "$stage"/
fi
printf '%s' "$ARCHIVE" | base64 -d | tar --no-same-owner -xzf - -C "$stage"
unset ARCHIVE
# A custom project name selects the existing Docker volumes. Carry it forward.
if [ -r "$INSTALL_PATH/.env" ]; then
    awk '/^[[:space:]]*(export[[:space:]]+)?COMPOSE_PROJECT_NAME[[:space:]]*=/' "$INSTALL_PATH/.env" >> "$stage/.env"
fi
chmod 700 "$stage"
chmod 600 "$stage/.env" "$stage/conf/nats/nats.conf" "$stage/conf/certs/proxy.key" "$stage/conf/traefik/certs/proxy.key"
# The regional collector runs unprivileged and reads the public CA from a directory mount.
chmod 711 "$stage/conf/certs"
chmod 644 "$stage/conf/apm/regional.yaml" "$stage/conf/certs/ca.crt"
(cd "$stage" && bash ./bootstrap.sh preflight "$INSTALL_PATH")

if [ -d "$INSTALL_PATH" ]; then
    backup=$(mktemp -d "$parent/.$name.backup.XXXXXX")
    mv -- "$INSTALL_PATH" "$backup/previous"
fi
# The candidate and destination share a filesystem, so promotion is a rename.
mv -- "$stage" "$INSTALL_PATH"
promoted=true
(cd "$INSTALL_PATH" && bash ./bootstrap.sh)
if [ -n "$backup" ]; then
    printf 'Previous Proxy configuration saved in %s\n' "$backup/previous"
fi
