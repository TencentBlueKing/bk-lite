/**
 * 契约 ↔ 插件 metrics.json 双向校验，并禁止仪表盘 config 手写哨兵魔法数。
 *
 * 用法（在 web/ 下）：
 *   pnpm exec tsx scripts/check-unavailable-contracts.ts
 */
import * as fs from 'node:fs';
import * as path from 'node:path';

import { METRIC_UNAVAILABLE_CONTRACTS } from '../src/app/monitor/dashboards/shared/unavailable-contract/registry';
import { buildDashboardQuery } from '../src/app/monitor/dashboards/shared/unavailable-contract/build-query';

const webRoot = path.resolve(process.cwd());
const repoRoot = path.resolve(webRoot, '..');
const snmpRoot = path.join(repoRoot, 'server/apps/monitor/support-files/plugins/Telegraf/snmp');
const dashboardObjectsRoot = path.join(webRoot, 'src/app/monitor/dashboards/objects');

/** 各对象仪表盘实际查询的、可能含哨兵的指标（与 config 对齐）。 */
const OBJECT_DASHBOARD_METRICS: Record<string, Set<string>> = {
  switch: new Set([
    'device_temperature_celsius',
    'device_voltage_volts',
    'device_optical_rx_power',
    'device_optical_tx_power',
    'device_fan_state',
    'device_psu_state'
  ]),
  router: new Set(['device_temperature_celsius', 'device_fan_state', 'device_psu_state']),
  loadbalance: new Set(['device_temperature_celsius', 'device_fan_state', 'device_psu_state'])
};

/** 从 PromQL 片段提取 != N 哨兵（忽略 != 0，多为缺位/无效零值过滤而非厂商哨兵）。 */
function extractSentinelNumbers(query: string): number[] {
  const found = new Set<number>();
  for (const match of query.matchAll(/!=\s*(-?\d+)/g)) {
    const value = Number(match[1]);
    if (value === 0) continue;
    found.add(value);
  }
  return [...found].sort((a, b) => a - b);
}

function readJson(file: string): { collect_type?: string; metrics?: Array<{ name?: string; query?: string }> } {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

const errors: string[] = [];

// 1) 契约 → 插件：evidence 存在，且 sentinels 出现在对应 metric 的 query 中（空哨兵的过滤契约除外）
for (const contract of METRIC_UNAVAILABLE_CONTRACTS) {
  const evidencePath = path.join(repoRoot, contract.evidence);
  if (!fs.existsSync(evidencePath)) {
    errors.push(`missing evidence file for ${contract.collectType}/${contract.metric}: ${contract.evidence}`);
    continue;
  }
  try {
    buildDashboardQuery(contract);
  } catch (err) {
    errors.push(String(err));
  }
  const json = readJson(evidencePath);
  if (json.collect_type && json.collect_type !== contract.collectType) {
    errors.push(
      `collectType mismatch for ${contract.metric}: contract=${contract.collectType} plugin=${json.collect_type}`
    );
  }
  const metric = (json.metrics || []).find((item) => item.name === contract.metric);
  if (!metric?.query) {
    errors.push(`evidence ${contract.evidence} has no metric ${contract.metric}`);
    continue;
  }
  const pluginSentinels = extractSentinelNumbers(metric.query);
  for (const sentinel of contract.sentinels) {
    if (!pluginSentinels.includes(sentinel)) {
      errors.push(
        `contract ${contract.collectType}/${contract.metric} sentinel ${sentinel} not found in plugin query: ${metric.query}`
      );
    }
  }
}

// 2) 插件 → 契约：该对象仪表盘会查的 metric 上的 != N 必须注册
for (const entry of fs.readdirSync(snmpRoot).sort()) {
  const file = path.join(snmpRoot, entry, 'metrics.json');
  if (!fs.existsSync(file)) continue;
  const json = readJson(file);
  const objectType = String(json.name || '').toLowerCase();
  const dashboardMetrics = OBJECT_DASHBOARD_METRICS[objectType];
  if (!dashboardMetrics) continue;
  const collectType = json.collect_type;
  if (!collectType) continue;
  for (const metric of json.metrics || []) {
    if (!metric.name || !dashboardMetrics.has(metric.name) || !metric.query) continue;
    const pluginSentinels = extractSentinelNumbers(metric.query);
    if (!pluginSentinels.length) continue;
    const contracts = METRIC_UNAVAILABLE_CONTRACTS.filter(
      (item) => item.collectType === collectType && item.metric === metric.name
    );
    if (!contracts.length) {
      errors.push(
        `plugin ${entry} ${metric.name} has sentinels [${pluginSentinels.join(',')}] but no dashboard contract`
      );
      continue;
    }
    const registered = new Set(contracts.flatMap((item) => item.sentinels));
    for (const sentinel of pluginSentinels) {
      if (!registered.has(sentinel)) {
        errors.push(
          `plugin ${entry} ${metric.name} sentinel ${sentinel} missing from contracts for ${collectType}`
        );
      }
    }
  }
}

// 3) 禁止 switch/router/loadbalance config 手写哨兵字面量 / unavailableSentinels
const forbiddenPatterns: Array<{ re: RegExp; label: string }> = [
  { re: /unavailableSentinels\s*:/, label: 'unavailableSentinels' },
  { re: /!=\s*65535/, label: '!= 65535' },
  { re: /!=\s*128/, label: '!= 128' },
  { re: /!=\s*-128/, label: '!= -128' },
  { re: /!=\s*-10000/, label: '!= -10000' },
  { re: /!=\s*-2147483648/, label: '!= -2147483648' },
  { re: /!=\s*2147483647/, label: '!= 2147483647' }
];

for (const objectName of ['switch', 'router', 'loadbalance']) {
  const configPath = path.join(dashboardObjectsRoot, objectName, 'config.ts');
  if (!fs.existsSync(configPath)) continue;
  const source = fs.readFileSync(configPath, 'utf8');
  for (const { re, label } of forbiddenPatterns) {
    if (re.test(source)) {
      errors.push(`${objectName}/config.ts still contains hardcoded ${label}; move to unavailable-contract registry`);
    }
  }
}

if (errors.length) {
  process.stderr.write(`unavailable-contract check failed (${errors.length}):\n`);
  for (const error of errors) {
    process.stderr.write(`  - ${error}\n`);
  }
  process.exit(1);
}

process.stdout.write(
  `unavailable-contract check passed (${METRIC_UNAVAILABLE_CONTRACTS.length} contracts)\n`
);
