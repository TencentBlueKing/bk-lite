/**
 * CMDB 采集任务 IP 范围上限：开放到 /21（2048 个地址）。
 * 前缀锁定八位组数 = floor(minPrefix / 8)，/21 时锁定前 2 段，第 3、4 段可编辑。
 */
export const IP_RANGE_MIN_PREFIX = 21;
export const IP_RANGE_MAX_SIZE = 2 ** (32 - IP_RANGE_MIN_PREFIX);
export const IP_RANGE_LOCKED_PREFIX_OCTETS = Math.floor(IP_RANGE_MIN_PREFIX / 8);
/** 超过该地址数时，在 IP 范围下方提示拉长采集周期（不阻断提交）。 */
export const IP_RANGE_CYCLE_HINT_THRESHOLD = 255;

export function ipToNumber(ip: string): number {
  return ip.split('.').reduce((acc, curr) => acc * 256 + Number(curr), 0);
}

/** Inclusive address count; returns 0 when either side is incomplete/invalid. */
export function ipRangeSize(beginIp: string, endIp: string): number {
  if (!beginIp || !endIp) return 0;
  const begin = ipToNumber(beginIp);
  const end = ipToNumber(endIp);
  if (Number.isNaN(begin) || Number.isNaN(end) || end < begin) return 0;
  return end - begin + 1;
}

export function isIpRangeOrderValid(beginIp: string, endIp: string): boolean {
  if (!beginIp || !endIp) return true;
  return ipToNumber(endIp) >= ipToNumber(beginIp);
}

export function isIpRangeWithinLimit(
  beginIp: string,
  endIp: string,
  maxSize: number = IP_RANGE_MAX_SIZE,
): boolean {
  const size = ipRangeSize(beginIp, endIp);
  return size > 0 && size <= maxSize;
}
