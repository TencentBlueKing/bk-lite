/**
 * 仪表盘无后端预览：按指标语义生成合成时序数据。
 *
 * 返回结构对齐后端 query_range 契约：
 *   { data: { result: [ { metric: {<labels>}, values: [[unixSec, "value"], ...] } ] } }
 * renderChart 读取 result[].values（[秒级时间戳, 字符串数值]）与 result[].metric（维度 label）。
 */

const POINT_COUNT = 80;
const STEP_SEC = 60;

// 稳定的伪随机：同一 seed 每次渲染产出同一条曲线，截图不抖动。
const makeRng = (seed: number) => {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
};

const hash = (text: string): number => {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
};

// 从 query 中提取主指标标识符，用于语义判定 + 随机种子。
const extractMetricKey = (query: string): string => {
  const match = query.match(/[a-zA-Z_][a-zA-Z0-9_]*/g);
  if (!match) return query;
  const skip = new Set(['clamp_min', 'clamp_max', 'sum', 'avg', 'rate', 'by', 'count', 'max', 'min']);
  return match.find((token) => !skip.has(token)) || match[0];
};

interface ShapeSpec {
  base: number;
  amplitude: number;
  noise: number;
  trend: number; // 每点的线性漂移
  min: number;
  max: number;
}

// 按单位 + 指标名关键字推断曲线形态，让效果图接近真实观感。
const resolveShape = (unit: string, key: string, rng: () => number): ShapeSpec => {
  const k = key.toLowerCase();
  const u = (unit || '').toLowerCase();

  if (u === 'percent') {
    // 使用率类：0-100 之间波动，CPU/io wait 偏低，内存偏高。
    if (k.includes('iowait') || k.includes('system') || k.includes('other')) {
      return { base: 4 + rng() * 6, amplitude: 3, noise: 1.5, trend: 0, min: 0, max: 100 };
    }
    if (k.includes('mem')) {
      return { base: 55 + rng() * 20, amplitude: 6, noise: 2, trend: 0.05, min: 0, max: 100 };
    }
    return { base: 25 + rng() * 25, amplitude: 12, noise: 4, trend: 0, min: 0, max: 100 };
  }

  if (u === 'bytes' || u === 'mebibytes') {
    const gb = 1024 * 1024 * 1024;
    if (k.includes('total')) {
      // 总容量：近似常量。
      return { base: 16 * gb, amplitude: 0, noise: gb * 0.002, trend: 0, min: 0, max: 64 * gb };
    }
    if (k.includes('avail') || k.includes('free')) {
      return { base: 7 * gb, amplitude: gb * 0.8, noise: gb * 0.15, trend: -gb * 0.01, min: 0, max: 16 * gb };
    }
    return { base: 6 * gb, amplitude: gb * 0.6, noise: gb * 0.1, trend: gb * 0.01, min: 0, max: 16 * gb };
  }

  if (u === 'byteps' || u === 'cps' || u === 'ops' || u === 'iops') {
    // 吞吐类：带尖峰。
    return { base: 1.5e6, amplitude: 2.5e6, noise: 6e5, trend: 0, min: 0, max: Number.MAX_SAFE_INTEGER };
  }

  if (u === 'ms') {
    return { base: 12 + rng() * 20, amplitude: 8, noise: 4, trend: 0, min: 0, max: Number.MAX_SAFE_INTEGER };
  }

  // none / 负载类：0-4 区间。
  if (k.includes('load')) {
    const factor = k.includes('15') ? 0.6 : k.includes('5') ? 0.8 : 1;
    return { base: (0.8 + rng()) * factor, amplitude: 0.5 * factor, noise: 0.2, trend: 0, min: 0, max: 64 };
  }

  return { base: 10 + rng() * 40, amplitude: 8, noise: 3, trend: 0, min: 0, max: Number.MAX_SAFE_INTEGER };
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

// 枚举/状态指标:预览产出合法枚举码,使详情行显示状态文案 + 语义色(否则退化成无意义数字)。
// 用 query 子串匹配,避开与计数指标的碰撞(如 *_status_restart_count 不含下列子串)。
const ENUM_METRIC_SAMPLE: Array<{ match: string; code: number }> = [
  { match: 'health_checks_status', code: 2 }  // consul 整体状态 → 危险(红)
];

const buildSeries = (query: string, unit: string) => {
  const key = extractMetricKey(query);
  const rng = makeRng(hash(query));

  const enumHit = ENUM_METRIC_SAMPLE.find((e) => query.includes(e.match));
  if (enumHit) {
    const endSecEnum = Math.floor(Date.now() / 1000 / STEP_SEC) * STEP_SEC;
    const enumValues: [number, string][] = [];
    for (let i = 0; i < POINT_COUNT; i += 1) {
      enumValues.push([endSecEnum - (POINT_COUNT - 1 - i) * STEP_SEC, String(enumHit.code)]);
    }
    return enumValues;
  }

  const shape = resolveShape(unit, key, rng);

  const endSec = Math.floor(Date.now() / 1000 / STEP_SEC) * STEP_SEC;
  const phase = rng() * Math.PI * 2;
  const period = 12 + rng() * 18;

  const values: [number, string][] = [];
  for (let i = 0; i < POINT_COUNT; i += 1) {
    const ts = endSec - (POINT_COUNT - 1 - i) * STEP_SEC;
    const wave = Math.sin((i / period) * Math.PI * 2 + phase) * shape.amplitude;
    const spike = rng() > 0.92 ? shape.amplitude * (0.6 + rng()) : 0;
    const raw = shape.base + wave + spike + (rng() - 0.5) * 2 * shape.noise + shape.trend * i;
    const value = clamp(raw, shape.min, shape.max);
    values.push([ts, String(Number(value.toFixed(value < 100 ? 2 : 0)))]);
  }
  return values;
};

/**
 * 模拟 getInstanceQuery：根据 SearchParams 返回合成 query_range 结果。
 * 采集状态查询（count(...) by (instance_id)）返回常量在线值。
 */
export const buildSyntheticQueryResult = (params: { query?: string; source_unit?: string } = {}) => {
  const query = params.query || '';
  const unit = params.source_unit || 'none';

  const isCollectionStatus = /count\s*\(/.test(query) && /by\s*\(/.test(query);
  if (isCollectionStatus) {
    const endSec = Math.floor(Date.now() / 1000 / STEP_SEC) * STEP_SEC;
    const values: [number, string][] = [];
    for (let i = 0; i < POINT_COUNT; i += 1) {
      values.push([endSec - (POINT_COUNT - 1 - i) * STEP_SEC, '1']);
    }
    return { data: { result: [{ metric: { instance_id: 'mock-instance-1' }, values }] } };
  }

  return {
    data: {
      result: [
        {
          metric: { instance_id: 'mock-instance-1', __name__: extractMetricKey(query) },
          values: buildSeries(query, unit)
        }
      ]
    }
  };
};

// 模拟 getInstanceList：提供 2 个可切换实例，验证实例选择器。
export const buildSyntheticInstanceList = () => ({
  count: 2,
  results: [
    {
      instance_id: 'mock-instance-1',
      instance_name: 'mock-host-01',
      instance_id_values: ['mock-instance-1'],
      instance_id_keys: ['instance_id']
    },
    {
      instance_id: 'mock-instance-2',
      instance_name: 'mock-host-02',
      instance_id_values: ['mock-instance-2'],
      instance_id_keys: ['instance_id']
    }
  ]
});
