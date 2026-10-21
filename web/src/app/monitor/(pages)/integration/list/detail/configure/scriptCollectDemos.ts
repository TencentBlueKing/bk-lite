export type ScriptDemoId =
  | 'linux_host'
  | 'windows_host'
  | 'process_port'
  | 'python_biz';

export interface ScriptCollectDemoResolved {
  id: ScriptDemoId;
  os: 'linux' | 'windows';
  interpreter: string;
  body: string;
}

export const SCRIPT_PROM_TEXT_EXAMPLE = 'demo_cpu_usage{cpu="0"} 12.5';

export const SCRIPT_COLLECT_DEMO_BUTTONS: Array<{
  id: ScriptDemoId;
  labelKey: string;
  defaultLabel: string;
}> = [
  {
    id: 'linux_host',
    labelKey: 'monitor.integrations.scriptDemoLinuxHost',
    defaultLabel: 'Linux 基础资源'
  },
  {
    id: 'windows_host',
    labelKey: 'monitor.integrations.scriptDemoWindowsHost',
    defaultLabel: 'Windows 基础资源'
  },
  {
    id: 'process_port',
    labelKey: 'monitor.integrations.scriptDemoProcessPort',
    defaultLabel: '进程/端口存活'
  },
  {
    id: 'python_biz',
    labelKey: 'monitor.integrations.scriptDemoPythonBiz',
    defaultLabel: 'Python 业务指标'
  }
];

export const LINUX_HOST_SCRIPT = [
  "# Linux host resources demo.",
  "# Optional env: DISK_MOUNT (default /).",
  "# Output Prometheus text only. No timestamps. Do not use reserved tag names.",
  "mount=\"${DISK_MOUNT:-/}\"",
  "mount_label=$(printf '%s' \"$mount\" | sed 's/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g')",
  "",
  "cpu_pct=$(awk '",
  "/^cpu / {",
  "  idle = $5 + $6",
  "  total = 0",
  "  for (i = 2; i <= NF; i++) total += $i",
  "  if (total <= 0) print 0",
  "  else printf \"%.2f\", (total - idle) * 100 / total",
  "  exit",
  "}",
  "' /proc/stat)",
  "[ -n \"$cpu_pct\" ] || cpu_pct=0",
  "",
  "mem_pct=$(awk '",
  "/^MemTotal:/ { t = $2 }",
  "/^MemAvailable:/ { a = $2 }",
  "END {",
  "  if (t <= 0) print 0",
  "  else printf \"%.2f\", (t - a) * 100 / t",
  "}",
  "' /proc/meminfo)",
  "[ -n \"$mem_pct\" ] || mem_pct=0",
  "",
  "disk_pct=$(df -P \"$mount\" 2>/dev/null | awk 'NR == 2 { gsub(\"%\", \"\", $5); print $5 + 0 }')",
  "[ -n \"$disk_pct\" ] || disk_pct=0",
  "",
  "load1=$(awk '{ print $1 }' /proc/loadavg)",
  "[ -n \"$load1\" ] || load1=0",
  "",
  "echo \"# TYPE host_cpu_usage_percent gauge\"",
  "echo \"host_cpu_usage_percent $cpu_pct\"",
  "echo \"# TYPE host_memory_used_percent gauge\"",
  "echo \"host_memory_used_percent $mem_pct\"",
  "echo \"# TYPE host_disk_used_percent gauge\"",
  "echo \"host_disk_used_percent{mount=\\\"$mount_label\\\"} $disk_pct\"",
  "echo \"# TYPE host_load1 gauge\"",
  "echo \"host_load1 $load1\""
].join('\n');

export const WINDOWS_HOST_SCRIPT = [
  "$ErrorActionPreference = 'SilentlyContinue'",
  "$drive = if ($env:DISK_DRIVE) { $env:DISK_DRIVE } else { 'C:' }",
  "if ($drive -notmatch ':$') { $drive = $drive + ':' }",
  "",
  "function Get-PromNumber {",
  "  param([scriptblock]$Probe)",
  "  try {",
  "    $value = & $Probe",
  "    if ($null -eq $value -or $value -eq '') { return [double]0 }",
  "    return [double]$value",
  "  } catch {",
  "    return [double]0",
  "  }",
  "}",
  "",
  "function Format-PromValue {",
  "  param([double]$Number)",
  "  return $Number.ToString('0.##', [System.Globalization.CultureInfo]::InvariantCulture)",
  "}",
  "",
  "$cpu = Get-PromNumber {",
  "  $p = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average",
  "  [math]::Round($p.Average, 2)",
  "}",
  "$mem = Get-PromNumber {",
  "  $os = Get-CimInstance Win32_OperatingSystem",
  "  if ($os.TotalVisibleMemorySize -le 0) { return 0 }",
  "  [math]::Round((($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 100.0 / $os.TotalVisibleMemorySize), 2)",
  "}",
  "$disk = Get-PromNumber {",
  "  $d = Get-CimInstance Win32_LogicalDisk -Filter (\"DeviceID='$drive'\")",
  "  if (-not $d -or $d.Size -le 0) { return 0 }",
  "  [math]::Round((($d.Size - $d.FreeSpace) * 100.0 / $d.Size), 2)",
  "}",
  "$uptime = Get-PromNumber {",
  "  $os = Get-CimInstance Win32_OperatingSystem",
  "  [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalSeconds, 0)",
  "}",
  "",
  "$driveLabel = ([string]$drive).Replace('\\', '\\\\').Replace('\"', '\\\"')",
  "Write-Output \"# TYPE host_cpu_usage_percent gauge\"",
  "Write-Output (\"host_cpu_usage_percent \" + (Format-PromValue $cpu))",
  "Write-Output \"# TYPE host_memory_used_percent gauge\"",
  "Write-Output (\"host_memory_used_percent \" + (Format-PromValue $mem))",
  "Write-Output \"# TYPE host_disk_used_percent gauge\"",
  "Write-Output (\"host_disk_used_percent{drive=`\"\" + $driveLabel + \"`\"} \" + (Format-PromValue $disk))",
  "Write-Output \"# TYPE host_uptime_seconds gauge\"",
  "Write-Output (\"host_uptime_seconds \" + (Format-PromValue $uptime))"
].join('\n');

export const LINUX_PROCESS_PORT_SCRIPT = [
  "# Process / port liveness demo.",
  "# Optional env: PROCESS_NAME (default sshd), LISTEN_PORT (default 22).",
  "name=\"${PROCESS_NAME:-sshd}\"",
  "port=\"${LISTEN_PORT:-22}\"",
  "name_label=$(printf '%s' \"$name\" | sed 's/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g')",
  "port_label=$(printf '%s' \"$port\" | sed 's/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g')",
  "",
  "proc_up=0",
  "if command -v pgrep >/dev/null 2>&1; then",
  "  pgrep -x \"$name\" >/dev/null 2>&1 && proc_up=1",
  "else",
  "  ps -eo comm= 2>/dev/null | awk -v n=\"$name\" '$0 == n { found = 1 } END { exit !found }' && proc_up=1",
  "fi",
  "",
  "port_up=0",
  "if command -v ss >/dev/null 2>&1; then",
  "  ss -lnt 2>/dev/null | awk -v p=\":$port\" 'NR > 1 && index($4, p) { found = 1 } END { exit !found }' && port_up=1",
  "elif command -v netstat >/dev/null 2>&1; then",
  "  netstat -lnt 2>/dev/null | awk -v p=\":$port\" 'index($0, p) { found = 1 } END { exit !found }' && port_up=1",
  "fi",
  "",
  "echo \"# TYPE process_up gauge\"",
  "echo \"process_up{name=\\\"$name_label\\\"} $proc_up\"",
  "echo \"# TYPE port_listen_up gauge\"",
  "echo \"port_listen_up{port=\\\"$port_label\\\"} $port_up\""
].join('\n');

export const WINDOWS_PROCESS_PORT_SCRIPT = [
  "$ErrorActionPreference = 'SilentlyContinue'",
  "$procName = if ($env:PROCESS_NAME) { $env:PROCESS_NAME } else { 'svchost' }",
  "$port = if ($env:LISTEN_PORT) { $env:LISTEN_PORT } else { '135' }",
  "",
  "$procUp = 0",
  "if (Get-Process -Name $procName -ErrorAction SilentlyContinue) { $procUp = 1 }",
  "",
  "$portUp = 0",
  "try {",
  "  $portNumber = [int]$port",
  "  $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue",
  "  if ($listeners | Where-Object { $_.LocalPort -eq $portNumber }) { $portUp = 1 }",
  "} catch {}",
  "",
  "$procLabel = ([string]$procName).Replace('\\', '\\\\').Replace('\"', '\\\"')",
  "$portLabel = ([string]$port).Replace('\\', '\\\\').Replace('\"', '\\\"')",
  "Write-Output \"# TYPE process_up gauge\"",
  "Write-Output (\"process_up{name=`\"\" + $procLabel + \"`\"} \" + $procUp)",
  "Write-Output \"# TYPE port_listen_up gauge\"",
  "Write-Output (\"port_listen_up{port=`\"\" + $portLabel + \"`\"} \" + $portUp)"
].join('\n');

export const PYTHON_BIZ_SCRIPT = [
  "import os",
  "",
  "service = os.environ.get(\"SERVICE_NAME\", \"demo\")",
  "service = service.replace(\"\\\\\", \"\\\\\\\\\").replace('\"', '\\\\\"')",
  "try:",
  "    depth = float(os.environ.get(\"QUEUE_DEPTH\", \"0\"))",
  "except ValueError:",
  "    depth = 0.0",
  "",
  "print(\"# TYPE demo_service_up gauge\")",
  "print('demo_service_up{service=\"%s\"} 1' % service)",
  "print(\"# TYPE demo_queue_depth gauge\")",
  "print('demo_queue_depth{service=\"%s\"} %.2f' % (service, depth))",
  "print(\"# TYPE demo_request_latency_ms gauge\")",
  "print('demo_request_latency_ms{service=\"%s\",quantile=\"0.99\"} 12.5' % service)"
].join('\n');


const normalizeOs = (os: unknown): 'linux' | 'windows' =>
  os === 'windows' ? 'windows' : 'linux';

export const defaultDemoIdForOs = (os: unknown): ScriptDemoId =>
  normalizeOs(os) === 'windows' ? 'windows_host' : 'linux_host';

export const resolveScriptCollectDemo = (
  id: ScriptDemoId,
  currentOs: unknown
): ScriptCollectDemoResolved => {
  if (id === 'linux_host') {
    return {
      id,
      os: 'linux',
      interpreter: '/bin/sh',
      body: LINUX_HOST_SCRIPT
    };
  }
  if (id === 'windows_host') {
    return {
      id,
      os: 'windows',
      interpreter: 'powershell.exe',
      body: WINDOWS_HOST_SCRIPT
    };
  }
  const os = normalizeOs(currentOs);
  if (id === 'python_biz') {
    return {
      id,
      os,
      interpreter: os === 'windows' ? 'python.exe' : '/usr/bin/python3',
      body: PYTHON_BIZ_SCRIPT
    };
  }
  return {
    id,
    os,
    interpreter: os === 'windows' ? 'powershell.exe' : '/bin/sh',
    body: os === 'windows' ? WINDOWS_PROCESS_PORT_SCRIPT : LINUX_PROCESS_PORT_SCRIPT
  };
};

const normalizeScriptBody = (script: unknown) => String(script || '').replace(/\s+$/, '');

export const matchingScriptDemoId = (
  script: unknown,
  currentOs: unknown
): ScriptDemoId | undefined => {
  const body = normalizeScriptBody(script);
  if (!body) return undefined;
  return SCRIPT_COLLECT_DEMO_BUTTONS.map((item) => item.id).find(
    (id) => normalizeScriptBody(resolveScriptCollectDemo(id, currentOs).body) === body
  );
};
