import assert from 'node:assert/strict';
import { formatNetworkMetricValue } from '../src/app/ops-analysis/(pages)/view/networkTopology/utils/metricValueFormat';

const cases: Array<[string, string, number, string]> = [
  ['lowercase megabits/sec scales as rate', 'mbps', 1000, '1 Gbps'],
  ['kilobits/sec keeps WeOps Kbits factor', 'Kbits', 1500, '1.5 Mbps'],
  ['packets/sec uses SI scaling', 'pps', 1500, '1.5 Kpps'],
  ['bytes/sec stays byte based instead of bits based', 'Bps', 1500, '1.5 KBps'],
  ['WeOps bits uses IEC bit scaling', 'bits', 2048, '2 Kib'],
  ['WeOps decbits uses SI bit scaling', 'decbits', 2000, '2 Kb'],
  ['WeOps bytes uses IEC scaling', 'bytes', 1536, '1.5 KiB'],
  ['decimal megabytes scale from MB', 'decmbytes', 1536, '1.54 GB'],
  ['seconds scale to larger time units', 's', 3600, '1 h'],
  ['percentunit converts ratio to percent', 'percentunit', 0.42, '42%'],
  ['WeOps short unit remains compact count', 'short', 1341088462, '1.34 Bil'],
];

for (const [name, unit, value, expected] of cases) {
  assert.equal(
    formatNetworkMetricValue(value, unit),
    expected,
    name,
  );
}

console.log('network topology metric value format tests passed');
