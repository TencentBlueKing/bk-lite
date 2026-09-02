# Host AIX

This is **local AIX OS monitoring** on the Host object. Collection uses system commands; missing commands are skipped. There is no version picker on the form. OS level comes from `oslevel -r` (for example `7100-00`). After you save, the platform prepares collection on the target host and then pulls metrics on the interval.

What is collected: CPU (including LPAR entitled capacity and online virtual CPUs), memory and paging, svmon categories (including pin), load 1 / 5 / 15, process states (SysV `ps` column `s`; skipped if the command or column is missing), disk capacity and IO / busy, NICs, and uptime. Hardware inventory, lastlog, lsof, and connection tables are not collected.

## How to use

1. Pick a collect node that can reach the AIX host.
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
| Node | Yes | Node that runs collection. |

After deploy, run `plugin_init` if this plugin is not yet in the console.
