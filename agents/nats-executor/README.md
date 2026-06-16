# NATS Executor

NATS Executor is a cross-platform executor for local commands, remote SSH commands, and remote file transfer.

## Runtime Configuration

| Environment variable | Required | Description |
| --- | --- | --- |
| `NATS_URLS` | Yes | NATS server URLs. Use a `tls:` URL to enable TLS config rendering in `support-files/startup.sh`. |
| `NATS_INSTANCE_ID` | Yes | Executor instance ID used for NATS subscriptions. |
| `NATS_CA_FILE` | Required for TLS | CA file used when `NATS_URLS` starts with `tls:`. |
| `SSH_KNOWN_HOSTS_FILE` | No | Enables SSH/SCP host key verification when set to a known_hosts file path. |

## SSH Host Key Verification

By default, SSH execution and SCP transfer keep the historical compatibility behavior and do not verify remote host identity. Set `SSH_KNOWN_HOSTS_FILE` to enable strict host key verification for both paths.

```bash
SSH_KNOWN_HOSTS_FILE=/etc/nats-executor/known_hosts
```

When this variable is set:

- SSH execution uses the configured `known_hosts` file through Go's `knownhosts` verifier.
- SCP upload and download use `StrictHostKeyChecking=yes` and `UserKnownHostsFile=<path>`.
- Modern and legacy SSH compatibility retries both keep host key verification enabled.
- Connections fail when the target host is missing from the file or its key no longer matches.

Create or refresh the file with trusted host keys before enabling the variable:

```bash
mkdir -p /etc/nats-executor
ssh-keyscan -H -p 22 10.0.0.8 >> /etc/nats-executor/known_hosts
chmod 0644 /etc/nats-executor/known_hosts
```

Container example:

```bash
docker run \
  -e NATS_URLS="nats://admin:password@nats:4222" \
  -e NATS_INSTANCE_ID="executor-1" \
  -e SSH_KNOWN_HOSTS_FILE="/etc/nats-executor/known_hosts" \
  -v /etc/nats-executor/known_hosts:/etc/nats-executor/known_hosts:ro \
  bklite/nats-executor
```

Leave `SSH_KNOWN_HOSTS_FILE` unset if the deployment has not prepared trusted host keys yet. This preserves the previous compatibility behavior.

## Testing

```bash
go test ./ssh -count=1
```
