import assert from 'node:assert/strict';
import {
  IP_RANGE_CYCLE_HINT_THRESHOLD,
  IP_RANGE_LOCKED_PREFIX_OCTETS,
  IP_RANGE_MAX_SIZE,
  IP_RANGE_MIN_PREFIX,
  ipRangeSize,
  ipToNumber,
  isIpRangeOrderValid,
  isIpRangeWithinLimit,
} from '../src/app/cmdb/components/ipInput/ipRangeLimits';

assert.equal(IP_RANGE_MIN_PREFIX, 21);
assert.equal(IP_RANGE_MAX_SIZE, 2048);
assert.equal(IP_RANGE_LOCKED_PREFIX_OCTETS, 2);
assert.equal(IP_RANGE_CYCLE_HINT_THRESHOLD, 255);

assert.equal(ipToNumber('10.0.0.1'), 167772161);
assert.equal(ipRangeSize('10.0.0.1', '10.0.0.1'), 1);
assert.equal(ipRangeSize('10.0.0.1', '10.0.0.10'), 10);
// /21 满段：10.0.0.0 - 10.0.7.255 = 2048
assert.equal(ipRangeSize('10.0.0.0', '10.0.7.255'), 2048);
assert.equal(isIpRangeWithinLimit('10.0.0.0', '10.0.7.255'), true);
// 超出 /21
assert.equal(isIpRangeWithinLimit('10.0.0.0', '10.0.8.0'), false);
assert.equal(ipRangeSize('10.0.0.0', '10.0.8.0'), 2049);

assert.equal(isIpRangeOrderValid('10.0.1.10', '10.0.1.1'), false);
assert.equal(isIpRangeOrderValid('10.0.1.1', '10.0.5.200'), true);
// 跨第 3 段但仍在 /21 内
assert.equal(isIpRangeWithinLimit('10.0.1.1', '10.0.5.200'), true);

// 周期提示阈值：255 个不提示，256 个提示
assert.equal(ipRangeSize('10.0.0.1', '10.0.0.255') > IP_RANGE_CYCLE_HINT_THRESHOLD, false);
assert.equal(ipRangeSize('10.0.0.1', '10.0.1.0') > IP_RANGE_CYCLE_HINT_THRESHOLD, true);

console.log('CMDB IP 范围 /21 上限测试通过');
