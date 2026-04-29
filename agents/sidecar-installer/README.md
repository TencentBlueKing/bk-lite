# Sidecar Installer Build & Release Runbook

## Artifacts

- Windows installer filename: `bklite-controller-installer.exe`
- Linux installer filename: `bklite-controller-installer`

Default object storage layout:

- Latest path: `installer/<os>/<arch>/<filename>`

Examples:

- `installer/windows/x86_64/bklite-controller-installer.exe`
- `installer/linux/x86_64/bklite-controller-installer`
- `installer/linux/arm64/bklite-controller-installer`

## Build

From `agents/sidecar-installer/`:

```bash
make install-deps
make build
```

For release artifacts with both Linux architectures:

```bash
make release-artifacts
```

`make install-deps` will try to install build dependencies for:

- macOS: Homebrew
- Linux: `apt-get`, `dnf`, `yum`, `apk`, `pacman`, `zypper`
- Windows: `winget` or `choco`

Installed dependencies include Go, Python 3, Pillow, and NSIS.

To avoid Homebrew / PEP 668 system Python restrictions, Pillow is installed into a local virtualenv at `agents/sidecar-installer/.venv`, and subsequent build steps reuse that virtualenv automatically.

Outputs:

- Windows NSIS installer: `bklite-controller-installer.exe`
- Linux installer binary: `bklite-controller-installer`
- Release-ready Linux x86_64 binary: `dist/linux/x86_64/bklite-controller-installer`
- Release-ready Linux ARM64 binary: `dist/linux/arm64/bklite-controller-installer`
- Release-ready Windows x86_64 installer: `dist/windows/x86_64/bklite-controller-installer.exe`

Notes:

- `setup-worker.exe` is an internal Windows build artifact produced before NSIS packaging.
- The final distributable for Windows users is only `bklite-controller-installer.exe`.
- `bklite-controller-installer.exe` already embeds `setup-worker.exe`, extracts it during installation, uses it to perform the actual install steps, and then cleans it up.
- For release/upload, do not distribute `setup-worker.exe` separately.

## Upload

From `server/`:

```bash
python manage.py installer_init --os windows --cpu_architecture x86_64 --file_path /path/to/dist/windows/x86_64/bklite-controller-installer.exe
python manage.py installer_init --os linux --cpu_architecture x86_64 --file_path /path/to/dist/linux/x86_64/bklite-controller-installer
python manage.py installer_init --os linux --cpu_architecture arm64 --file_path /path/to/dist/linux/arm64/bklite-controller-installer
```

`installer_init` now uploads only the latest path and no longer accepts a version argument.

Upload behavior:

1. Uploads only to the latest path
2. Windows upload target: `installer/windows/x86_64/bklite-controller-installer.exe`
3. Linux x86_64 upload target: `installer/linux/x86_64/bklite-controller-installer`
4. Linux ARM64 upload target: `installer/linux/arm64/bklite-controller-installer`

## Controller / Collector package upload

From `server/`:

```bash
python manage.py controller_package_init --os linux --cpu_architecture x86_64 --object Controller --pk_version <version> --file_path /path/to/fusion-collectors-x86_64.tar.gz
python manage.py controller_package_init --os linux --cpu_architecture arm64 --object Controller --pk_version <version> --file_path /path/to/fusion-collectors-arm64.tar.gz
```

Collector packages also accept `--cpu_architecture` so the same package model can carry Linux x86_64 / ARM64 variants.

## Release-time verification

After uploading installers and controller packages:

```bash
python manage.py verify_architecture_rollout --version <version>
```

This command checks:

- Windows x86_64 installer latest path exists
- Linux x86_64 installer latest path exists
- Linux ARM64 installer latest path exists
- Linux x86_64 / ARM64 controller packages exist for the target version
- How many nodes still have empty `cpu_architecture`

## Historical node architecture backfill

If historical nodes were installed before CPU architecture was recorded, you can reuse the most recent controller-install SSH credentials to probe and backfill them:

```bash
python manage.py backfill_node_cpu_architecture --limit 100
python manage.py backfill_node_cpu_architecture --node-id <node_id>
python manage.py backfill_node_cpu_architecture --dry-run --limit 20
```

Behavior:

- Only targets nodes whose `cpu_architecture` is still empty
- Reuses the newest `ControllerTaskNode` SSH credentials for the same node IP/OS
- Linux detection uses `uname -m`
- Windows detection uses `cmd /c echo %PROCESSOR_ARCHITECTURE%`
- Nodes without reusable credentials are skipped rather than guessed

## Rollout Checklist

Execute the following in order when releasing Linux ARM64 controller support:

1. **Build installer artifacts**
   ```bash
   cd agents/sidecar-installer
   make release-artifacts
   ```
   Confirm these files exist:
   - `dist/windows/x86_64/bklite-controller-installer.exe`
   - `dist/linux/x86_64/bklite-controller-installer`
   - `dist/linux/arm64/bklite-controller-installer`

2. **Prepare controller packages for the same version**
   - Linux x86_64 controller package tarball
   - Linux ARM64 controller package tarball
   - Use the same `<version>` for both architectures

3. **Upload installer artifacts**
   ```bash
   cd server
   python manage.py installer_init --os windows --cpu_architecture x86_64 --file_path /path/to/dist/windows/x86_64/bklite-controller-installer.exe
   python manage.py installer_init --os linux --cpu_architecture x86_64 --file_path /path/to/dist/linux/x86_64/bklite-controller-installer
   python manage.py installer_init --os linux --cpu_architecture arm64 --file_path /path/to/dist/linux/arm64/bklite-controller-installer
   ```
   Note: Windows currently uploads only the x86_64 installer.

4. **Upload controller packages**
   ```bash
   python manage.py controller_package_init --os linux --cpu_architecture x86_64 --object Controller --pk_version <version> --file_path /path/to/fusion-collectors-x86_64.tar.gz
   python manage.py controller_package_init --os linux --cpu_architecture arm64 --object Controller --pk_version <version> --file_path /path/to/fusion-collectors-arm64.tar.gz
   ```

5. **Run release-time verification**
   ```bash
   python manage.py verify_architecture_rollout --version <version>
   ```
   Do not continue until this command confirms:
   - Windows x86_64 installer exists
   - Linux x86_64 installer exists
   - Linux ARM64 installer exists
   - Linux x86_64 controller package exists for `<version>`
   - Linux ARM64 controller package exists for `<version>`

6. **Validate live installation paths**
   - Validate one Linux x86_64 node with **curl/bootstrap** install
   - Validate one Linux ARM64 node with **curl/bootstrap** install
   - Validate one Linux x86_64 node with **remote install**
   - Validate one Linux ARM64 node with **remote install**
   - Confirm the installed node reports back `cpu_architecture` correctly in node management

7. **Check controller UI and node attributes**
   - Controller list distinguishes Linux `x86_64` and Linux `ARM64`
   - Node attributes show CPU architecture for newly installed/updated nodes

8. **Optionally backfill historical nodes**
   ```bash
   python manage.py backfill_node_cpu_architecture --dry-run --limit 20
   python manage.py backfill_node_cpu_architecture --limit 100
   ```
   Use `--node-id <node_id>` for targeted retry on important legacy nodes.

9. **Post-release monitoring**
   - Watch for failed ARM64 installs caused by missing artifacts or unsupported credentials
   - Track how many nodes still have empty `cpu_architecture`
   - Keep using `verify_architecture_rollout --version <version>` as a quick release sanity check

## Runtime APIs

### Installer session

- `GET /api/v1/node_mgmt/open_api/installer/session?token=...`

Returns the installer session consumed by both Windows and Linux installers.

### Installer manifest

- `GET /api/proxy/node_mgmt/api/installer/manifest/`

Returns latest artifact metadata for Windows and Linux.

### Installer metadata by OS

- `GET /api/proxy/node_mgmt/api/installer/metadata/windows/`
- `GET /api/proxy/node_mgmt/api/installer/metadata/linux/`

Returns latest artifact metadata for the target OS. Pass `?arch=x86_64` or `?arch=arm64` for architecture-specific installer metadata.

## Cloud Region Variables

Recommended direct-download variables:

- `NATS_SERVERS`
- `NATS_PROTOCOL`
- `NATS_TLS_CA`
- `NATS_DOWNLOAD_USERNAME`
- `NATS_DOWNLOAD_PASSWORD`
- `NATS_INSTALLER_BUCKET`

Fallbacks still exist, but the preferred model is a dedicated download-only credential and bucket.
