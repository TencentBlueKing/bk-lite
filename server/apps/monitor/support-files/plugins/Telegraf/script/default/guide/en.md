# Script Collection Guide

The node runs your custom script and reports metrics parsed from Prometheus text on standard output. Read the output format, `$` spelling, run-as user, and limits before you paste or insert a sample.

## Output format

Standard output must be Prometheus text, one sample per line, for example:

```
demo_cpu_usage{cpu="0"} 12.5
```

At most 50 samples. Trailing timestamps are ignored. Do not emit Influx line protocol or `key=value`.

## `$` in the script body

Write every `$` in the script body as `$$`. The sample templates on this page already follow that rule. For example:

- Environment variables: `$$KEY`, `$${KEY}`, `$$env:KEY`
- awk fields: `$$5`, `$$i`
- PowerShell variables: `$$cpu`

Python does not need `$` when it uses `os.environ.get("KEY")`.

## Environment variables

Set KEY and VALUE in Environment. Read them in the script as follows:

- Linux: `$$KEY` or `$${KEY}`
- Windows: `$$env:KEY`
- Python: `os.environ.get("KEY")`

## Run-as user

The Linux default run-as user is `telegraf`. That user must exist on the **collector** (the node / sidecar container), not on the platform web host. If the collector has no `telegraf` user, change **Run As** to an existing non-root user on the collector, or create that user there. Scripts cannot run as root.

Windows runs as the service account; Run As cannot be changed.

## Reserved labels

The platform writes these labels and overwrites the same names from script output. Use other label names:

`instance_id`, `instance_type`, `collect_type`, `config_type`, `plugin_id`, `agent_id`, `config_id`, `script`

## Limits

- Can only be bound to operating-system monitor objects
- Collection interval must be at least 60 seconds
- Timeout is the collection interval minus 1 second and cannot be longer
- Scripts cannot run as root on Linux
- Interpreters must be chosen from the whitelist: Linux `/bin/sh`, `/bin/bash`, `/usr/bin/python3`; Windows `powershell.exe`, `cmd.exe`, `python.exe`
- Metric names cannot start with `bklite_script_`
