export type ScriptDemoId =
  | 'linux_host'
  | 'windows_host'
  | 'python_biz';

export type ScriptLangTab = 'shell' | 'python' | 'powershell' | 'cmd';

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
    id: 'python_biz',
    labelKey: 'monitor.integrations.scriptDemoPythonBiz',
    defaultLabel: 'Python 业务指标'
  }
];

const SHELL_FORMAT_HEADER = [
  '#!/bin/sh',
  '#',
  'export LC_ALL=C',
  'export LANG=C',
  '#',
  '# 标准输出：一行一条指标，名称 {标签="值"} 数值',
  '# 例如：echo \'host_cpu_usage_percent{cpu="0"} 12.5\'',
  '#',
  '# 脚本里的美元符号请写成两个，例如 awk 字段用 $$5，环境变量用 $$KEY。',
  ''
].join('\n');

const POWERSHELL_FORMAT_HEADER = [
  '# 标准输出：一行一条指标，名称 {标签="值"} 数值',
  '# 例如：Write-Output \'host_cpu_usage_percent{cpu="0"} 12.5\'',
  '#',
  '# 脚本里的美元符号请写成两个，例如变量用 $$cpu，环境变量用 $$env:KEY。',
  ''
].join('\n');

const PYTHON_FORMAT_HEADER = [
  '# 标准输出：一行一条指标，名称 {标签="值"} 数值',
  '# 例如：print(\'host_cpu_usage_percent{cpu="0"} 12.5\')',
  '#',
  '# 环境变量用 os.environ.get("KEY") 读取，不需要美元符号。',
  ''
].join('\n');

export const LINUX_HOST_SCRIPT = [
  SHELL_FORMAT_HEADER,
  'echo "# TYPE host_cpu_usage_percent gauge"',
  "awk '",
  '/^cpu / {',
  '  idle = $$5 + $$6',
  '  total = $$2 + $$3 + $$4 + $$5 + $$6 + $$7 + $$8 + $$9 + $$10 + $$11',
  '  if (total <= 0) print "host_cpu_usage_percent 0"',
  '  else printf "host_cpu_usage_percent %.2f\\n", (total - idle) * 100 / total',
  '  done = 1',
  '  exit',
  '}',
  'END { if (!done) print "host_cpu_usage_percent 0" }',
  "' /proc/stat",
  '',
  'echo "# TYPE host_memory_used_percent gauge"',
  "awk '",
  '/^MemTotal:/ { t = $$2 }',
  '/^MemAvailable:/ { a = $$2 }',
  'END {',
  '  if (t <= 0) print "host_memory_used_percent 0"',
  '  else printf "host_memory_used_percent %.2f\\n", (t - a) * 100 / t',
  '}',
  "' /proc/meminfo",
  '',
  'echo "# TYPE host_disk_used_percent gauge"',
  'df -P / 2>/dev/null | awk \'NR == 2 { gsub("%", "", $$5); printf "host_disk_used_percent{mount=\\"/\\"} %d\\n", $$5 + 0; found = 1 } END { if (!found) print "host_disk_used_percent{mount=\\"/\\"} 0" }\'',
  '',
  'echo "# TYPE host_load1 gauge"',
  "awk '{ printf \"host_load1 %.2f\\n\", $$1 + 0 } END { if (NR < 1) print \"host_load1 0\" }' /proc/loadavg"
].join('\n');

export const WINDOWS_HOST_SCRIPT = [
  POWERSHELL_FORMAT_HEADER,
  "$$ErrorActionPreference = 'SilentlyContinue'",
  "$$drive = if ($$env:DISK_DRIVE) { $$env:DISK_DRIVE } else { 'C:' }",
  "if ($$drive -notmatch ':$$') { $$drive = $$drive + ':' }",
  '',
  'function Get-PromNumber {',
  '  param([scriptblock]$$Probe)',
  '  try {',
  '    $$value = & $$Probe',
  '    if ($$null -eq $$value -or $$value -eq \'\') { return [double]0 }',
  '    return [double]$$value',
  '  } catch {',
  '    return [double]0',
  '  }',
  '}',
  '',
  'function Format-PromValue {',
  '  param([double]$$Number)',
  "  return $$Number.ToString('0.##', [System.Globalization.CultureInfo]::InvariantCulture)",
  '}',
  '',
  '$$cpu = Get-PromNumber {',
  '  $$p = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average',
  '  [math]::Round($$p.Average, 2)',
  '}',
  '$$mem = Get-PromNumber {',
  '  $$os = Get-CimInstance Win32_OperatingSystem',
  '  if ($$os.TotalVisibleMemorySize -le 0) { return 0 }',
  '  [math]::Round((($$os.TotalVisibleMemorySize - $$os.FreePhysicalMemory) * 100.0 / $$os.TotalVisibleMemorySize), 2)',
  '}',
  '$$disk = Get-PromNumber {',
  '  $$d = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID=\'$$drive\'")',
  '  if (-not $$d -or $$d.Size -le 0) { return 0 }',
  '  [math]::Round((($$d.Size - $$d.FreeSpace) * 100.0 / $$d.Size), 2)',
  '}',
  '$$uptime = Get-PromNumber {',
  '  $$os = Get-CimInstance Win32_OperatingSystem',
  '  [math]::Round(((Get-Date) - $$os.LastBootUpTime).TotalSeconds, 0)',
  '}',
  '',
  '$$driveLabel = ([string]$$drive).Replace(\'\\\\\', \'\\\\\\\\\').Replace(\'"\', \'\\\\"\')',
  'Write-Output "# TYPE host_cpu_usage_percent gauge"',
  'Write-Output ("host_cpu_usage_percent " + (Format-PromValue $$cpu))',
  'Write-Output "# TYPE host_memory_used_percent gauge"',
  'Write-Output ("host_memory_used_percent " + (Format-PromValue $$mem))',
  'Write-Output "# TYPE host_disk_used_percent gauge"',
  'Write-Output ("host_disk_used_percent{drive=`"" + $$driveLabel + "`"} " + (Format-PromValue $$disk))',
  'Write-Output "# TYPE host_uptime_seconds gauge"',
  'Write-Output ("host_uptime_seconds " + (Format-PromValue $$uptime))'
].join('\n');

export const PYTHON_BIZ_SCRIPT = [
  PYTHON_FORMAT_HEADER,
  'import os',
  '',
  'service = os.environ.get("SERVICE_NAME", "demo")',
  'service = service.replace("\\\\", "\\\\\\\\").replace(\'"\', \'\\\\"\')',
  'try:',
  '    depth = float(os.environ.get("QUEUE_DEPTH", "0"))',
  'except ValueError:',
  '    depth = 0.0',
  '',
  'print("# TYPE demo_service_up gauge")',
  'print(\'demo_service_up{service="%s"} 1\' % service)',
  'print("# TYPE demo_queue_depth gauge")',
  'print(\'demo_queue_depth{service="%s"} %.2f\' % (service, depth))',
  'print("# TYPE demo_request_latency_ms gauge")',
  'print(\'demo_request_latency_ms{service="%s",quantile="0.99"} 12.5\' % service)'
].join('\n');

const normalizeOs = (os: unknown): 'linux' | 'windows' =>
  os === 'windows' ? 'windows' : 'linux';

export const languageTabsForOs = (
  os: unknown
): Array<{ key: ScriptLangTab; label: string }> => {
  if (normalizeOs(os) === 'windows') {
    return [
      { key: 'powershell', label: 'PowerShell' },
      { key: 'cmd', label: 'CMD' },
      { key: 'python', label: 'Python' }
    ];
  }
  return [
    { key: 'shell', label: 'Shell' },
    { key: 'python', label: 'Python' }
  ];
};

export const langTabFromInterpreter = (
  interpreter: unknown,
  os: unknown
): ScriptLangTab => {
  const value = String(interpreter || '').toLowerCase();
  if (value.includes('python')) return 'python';
  if (value.includes('cmd')) return 'cmd';
  if (value.includes('powershell') || normalizeOs(os) === 'windows') {
    return 'powershell';
  }
  return 'shell';
};

export const interpreterForLangTab = (
  tab: ScriptLangTab,
  os: unknown,
  currentInterpreter?: unknown
): string => {
  const windows = normalizeOs(os) === 'windows';
  if (tab === 'python') return windows ? 'python.exe' : '/usr/bin/python3';
  if (tab === 'cmd') return 'cmd.exe';
  if (tab === 'powershell' || windows) return 'powershell.exe';
  const current = String(currentInterpreter || '');
  if (current === '/bin/bash' || current === '/bin/sh') return current;
  return '/bin/sh';
};

export const editorModeFromInterpreter = (
  interpreter: unknown
): 'python' | 'powershell' | 'sh' => {
  const value = String(interpreter || '').toLowerCase();
  if (value.includes('python')) return 'python';
  if (value.includes('powershell')) return 'powershell';
  return 'sh';
};

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
  return {
    id: 'python_biz',
    os,
    interpreter: os === 'windows' ? 'python.exe' : '/usr/bin/python3',
    body: PYTHON_BIZ_SCRIPT
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
