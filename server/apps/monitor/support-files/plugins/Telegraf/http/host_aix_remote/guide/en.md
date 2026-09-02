# Host AIX Remote

This is **remote AIX OS monitoring** on the Host object. Each interval a Linux collect node SSH-connects to AIX and pulls metrics. It does not leave a long-running install on the target host. Collection uses system commands; missing commands are skipped. There is no version picker on the form. OS level comes from `oslevel -r` (for example `7100-00`).

This release **does not offer Host AIX local collection**. Local would mean picking an already-onboarded AIX node and running nats-executor / `local.execute` on it. AIX cannot currently be an onboarded sidecar / nats-executor node, so this release does not fake local via SSH, and the Host access page no longer shows a Host AIX local form that asks for SSH. Use this remote plugin only.

What is collected: CPU (including LPAR entitled capacity and online virtual CPUs), memory and paging, svmon categories (including pin), load 1 / 5 / 15, process states (SysV `ps` column `s`; skipped if the command or column is missing), disk capacity / inodes / IO / busy, NICs, and uptime. Hardware inventory, lastlog, lsof, and connection tables are not collected.

## How to use

1. Pick a Linux collect node that can reach the AIX host.
2. Fill in host IP, username, SSH authentication (password or key), and interval.
3. Save, wait one interval, and view data on Host.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | AIX address. |
| Username | Yes | Default `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Password auth needs a password; key auth needs a private key (passphrase optional). |
| Port | No | Default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Linux node that runs collection. |

After deploy, run `plugin_init` if this plugin is not yet in the console. Run the same command if a leftover Host AIX local access item is still visible.
