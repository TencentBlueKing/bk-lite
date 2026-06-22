import * as assert from 'node:assert/strict';
import {
  resolveCapability,
  isMetricVisible,
  type CapabilityMatrix
} from '../src/app/monitor/dashboards/shared/capability-matrix-core';
import { CAPABILITY_MATRIX } from '../src/app/monitor/dashboards/shared/capability-matrix.generated';

// 固定 fixture：snmp_cisco 全能力；通用 snmp 仅 uptime/cpu/memory/traffic（无 temperature）。
const FIXTURE: CapabilityMatrix = {
  switch: [
    { collectType: 'snmp', capabilities: ['uptime', 'cpu', 'memory', 'traffic'] },
    { collectType: 'snmp_cisco', capabilities: ['uptime', 'cpu', 'memory', 'temperature', 'fan', 'psu', 'traffic'] }
  ],
  router: [],
  firewall: [],
  loadbalance: []
};

// 1. 最长 collect_type 子串命中（snmp_cisco 优先于 snmp）
{
  const r = resolveCapability(FIXTURE, 'switch', "('snmp_cisco:1:2:10.0.0.1',)");
  assert.equal(r.matched, true);
  assert.equal(r.collectType, 'snmp_cisco');
}

// 2. 未知 collect_type（不含任何 snmp 子串）→ 未命中
{
  const r = resolveCapability(FIXTURE, 'switch', 'mysql_3306');
  assert.equal(r.matched, false);
}

// 3. 支持 + 有数据 → 可见
{
  const r = resolveCapability(FIXTURE, 'switch', "('snmp_cisco',)");
  assert.equal(isMetricVisible(r, 'switch', 'device_temperature_celsius', true), true);
}

// 4. 支持 + 无数据 → 仍可见（渲染 --，"采集坏了"语义）
{
  const r = resolveCapability(FIXTURE, 'switch', "('snmp_cisco',)");
  assert.equal(isMetricVisible(r, 'switch', 'device_temperature_celsius', false), true);
}

// 5. 不支持 + 有数据 → 隐藏（防串味）：通用 snmp 无 temperature
{
  const r = resolveCapability(FIXTURE, 'switch', "('snmp:1:2:10.0.0.9',)");
  assert.equal(r.collectType, 'snmp');
  assert.equal(isMetricVisible(r, 'switch', 'device_temperature_celsius', true), false);
}

// 6. 未命中品牌 → 回退到数据存在性
{
  const r = resolveCapability(FIXTURE, 'switch', 'mysql_3306');
  assert.equal(isMetricVisible(r, 'switch', 'device_cpu_usage', true), true);
  assert.equal(isMetricVisible(r, 'switch', 'device_cpu_usage', false), false);
}

// 7. 未分类指标（如错包）→ 回退到数据存在性，即使品牌命中
{
  const r = resolveCapability(FIXTURE, 'switch', "('snmp_cisco',)");
  assert.equal(isMetricVisible(r, 'switch', 'device_total_in_errors', true), true);
  assert.equal(isMetricVisible(r, 'switch', 'device_total_in_errors', false), false);
}

// 8. 生成矩阵不变量：snmp_cisco/switch 应含 cpu/memory/temperature/fan/psu/traffic。
{
  const ciscoSwitch = CAPABILITY_MATRIX.switch.find((e) => e.collectType === 'snmp_cisco');
  assert.ok(ciscoSwitch, 'snmp_cisco/switch present in generated matrix');
  for (const cap of ['uptime', 'cpu', 'memory', 'temperature', 'fan', 'psu', 'traffic'] as const) {
    assert.ok(ciscoSwitch!.capabilities.includes(cap), `cisco switch supports ${cap}`);
  }
  const checkpointFw = CAPABILITY_MATRIX.firewall.find((e) => e.collectType === 'snmp_checkpoint');
  assert.ok(checkpointFw, 'snmp_checkpoint/firewall present in generated matrix');
  assert.ok(!checkpointFw!.capabilities.includes('session'), 'checkpoint firewall has no session capability');
}

console.log('monitor capability matrix tests passed');
