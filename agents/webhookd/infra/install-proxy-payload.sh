# Appended to the generated installer after INSTALL_PATH and ARCHIVE.
parent=$(dirname "$INSTALL_PATH")
name=$(basename "$INSTALL_PATH")
mkdir -p "$parent"
exec 9>"$parent/.$name.install.lock"
flock -n 9 || { echo "Another Proxy installation is in progress" >&2; exit 1; }

txn="$parent/.$name.installing"
stage="$txn/stage"
previous="$txn/previous"
retained="$parent/.$name.rollback"
marker=.proxy-install-backup

if [ -e "$retained" ] || [ -L "$retained" ]; then
    if [ -L "$retained" ] || [ ! -d "$retained/previous" ] || [ ! -f "$retained/$marker" ]; then
        printf 'Unrecognized Proxy backup directory: %s\n' "$retained" >&2
        exit 1
    fi
fi
if [ -e "$txn" ] || [ -L "$txn" ]; then
    printf 'Review any interrupted Proxy installation in %s before retrying\n' "$txn" >&2
    exit 1
fi
apply_started=false

rollback() {
    local switched=false
    # The rename can finish before Bash dispatches a signal trap.
    # The staged directory disappears only once it reaches the live path.
    if [ ! -e "$stage" ] && [ -d "$INSTALL_PATH" ]; then
        switched=true
        if $apply_started && [ ! -f "$previous/docker-compose.yaml" ]; then
            (cd "$INSTALL_PATH" && docker compose down) || return 1
        fi
        mv -- "$INSTALL_PATH" "$stage" || return 1
    fi
    if [ -d "$previous" ]; then
        # Never nest the previous installation inside a directory at the live path.
        [ ! -e "$INSTALL_PATH" ] && [ ! -L "$INSTALL_PATH" ] || return 1
        mv -- "$previous" "$INSTALL_PATH" || return 1
        if $switched && $apply_started && [ -f "$INSTALL_PATH/docker-compose.yaml" ]; then
            (cd "$INSTALL_PATH" && docker compose up -d --force-recreate) || return 1
        fi
    fi
}

cleanup() {
    local result=$?
    trap '' INT TERM
    if [ "$result" -ne 0 ]; then
        if ! rollback; then
            printf 'Proxy rollback could not finish. Check %s and the installation path.\n' "$txn" >&2
            exit "$result"
        fi
    elif [ -d "$previous" ]; then
        # Only rotate the fixed, installer-owned slot under the install lock.
        # Older versioned backups and alternate paths belong to the operator.
        if [ -e "$retained" ]; then
            rm -rf -- "$retained" || exit 1
        fi
        mv -- "$txn" "$retained" || exit 1
        printf 'Previous Proxy configuration saved in %s/previous\n' "$retained"
        exit 0
    fi
    rm -rf -- "$txn"
    exit "$result"
}
# Until staging exists, only empty work directories belong to this attempt.
trap 'rmdir -- "$stage" "$txn" 2>/dev/null || :' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -- "$txn"
mkdir -- "$stage"
trap cleanup EXIT
touch "$txn/$marker"

used_kib=0
if [ -e "$INSTALL_PATH" ] || [ -L "$INSTALL_PATH" ]; then
    if [ ! -d "$INSTALL_PATH" ] || [ -L "$INSTALL_PATH" ]; then
        echo "Proxy install path must be a regular directory" >&2
        exit 1
    fi
    if [ -n "$(find "$INSTALL_PATH" -type l -print -quit)" ]; then
        echo "Proxy install directory contains a symbolic link. Review the upgrade manually." >&2
        exit 1
    fi
    used_kib=$(du -sk -- "$INSTALL_PATH" | awk '{ print $1 }')
fi
archive_bytes=$(printf '%s' "$ARCHIVE" | base64 -d | gzip -dc | wc -c)
free_kib=$(df -Pk "$parent" | awk 'NR == 2 { print $4 }')
# Cover the expanded archive, staged copy, and filesystem overhead. The binary
# copy checks its own space after the collector image is available.
if (( free_kib < used_kib + (archive_bytes + 1023) / 1024 + 65536 )); then
    echo "Insufficient free space to stage the Proxy installation (including 64 MiB reserve)" >&2
    exit 1
fi

if [ -d "$INSTALL_PATH" ]; then
    cp -a -- "$INSTALL_PATH"/. "$stage"/
fi
printf '%s' "$ARCHIVE" | base64 -d | tar --no-same-owner -xzf - -C "$stage"
unset ARCHIVE
if [ -r "$INSTALL_PATH/.env" ]; then
    # Keep definitions used by local Compose overrides. Package keys win; write
    # them first so local definitions can interpolate the fresh values. Keep
    # complete quoted values, including embedded lines that look like assignments.
    awk '
        function assignment(line) {
            return match(line, /^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_.-]*[[:space:]]*[:=]/)
        }
        function key(line) {
            sub(/^[[:space:]]*(export[[:space:]]+)?/, "", line)
            sub(/[[:space:]]*[:=]$/, "", line)
            return line
        }
        function opens_quote(ch) { return ch == "\047" || ch == "\"" }
        function scan(text,   i, ch) {
            for (i = 1; i <= length(text); i++) {
                ch = substr(text, i, 1)
                if (ch == "\\" && substr(text, i+1, 1) == quote) {
                    i++
                } else if (ch == quote) {
                    quote = ""
                    return
                } else if (ch == "\\" && quote == "\"" && substr(text, i+1, 1) == "\\") {
                    i++
                }
            }
        }
        FNR == 1 && FILENAME == ARGV[2] {
            if (quote != "") exit 1
            print ""
        }
        {
            package = FILENAME == ARGV[1]
            if (quote != "") {
                if (!skip_line) print
                scan($0)
                next
            }
            skip_line = 0
            if (assignment($0)) {
                var = key(substr($0, 1, RLENGTH))
                if (package) managed[var] = 1
                else skip_line = (var in managed)
                value = substr($0, RLENGTH+1)
                sub(/^[[:space:]]*/, "", value)
                if (opens_quote(substr(value, 1, 1))) {
                    quote = substr(value, 1, 1)
                    scan(substr(value, 2))
                }
            }
            if (!skip_line) print
        }
        END { if (quote != "") exit 1 }
    ' "$stage/.env" "$INSTALL_PATH/.env" > "$txn/merged.env"
    mv -- "$txn/merged.env" "$stage/.env"
fi
chmod 700 "$stage"
chmod 600 "$stage/.env" "$stage/conf/nats/nats.conf" "$stage/conf/certs/proxy.key" "$stage/conf/traefik/certs/proxy.key"
# The regional collector runs unprivileged and reads the public CA from a directory mount.
chmod 711 "$stage/conf/certs"
chmod 644 "$stage/conf/apm/regional.yaml" "$stage/conf/certs/ca.crt"
(cd "$stage" && bash ./bootstrap.sh preflight "$INSTALL_PATH")

if [ -d "$INSTALL_PATH" ]; then
    mv -- "$INSTALL_PATH" "$previous"
fi
# The candidate and destination share a filesystem, so promotion is a rename.
mv -- "$stage" "$INSTALL_PATH"
apply_started=true
(cd "$INSTALL_PATH" && bash ./bootstrap.sh)
