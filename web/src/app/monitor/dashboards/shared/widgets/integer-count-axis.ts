export interface IntegerCountAxis {
  min: 0;
  max: number;
  interval: number;
}

const NICE_STEPS = [1, 2, 5, 10] as const;

/** 把粗步长收到 1/2/5×10^n，结果始终是正整数。 */
const niceIntegerStep = (rough: number) => {
  const step = Math.max(1, Math.round(rough));
  const exp = Math.floor(Math.log10(step));
  const base = 10 ** exp;
  const fraction = step / base;
  const picked = NICE_STEPS.find((item) => item >= fraction - 1e-9) ?? 10;
  return picked * base;
};

/**
 * 计数纵轴。刻度只落在整数上，上限至少为 1。
 * 避免 echarts 在 3 × 1.1 这类上限上打出 3.3000000000000003。
 */
export const integerCountAxis = (samples: readonly number[]): IntegerCountAxis => {
  let peak = 0;
  samples.forEach((value) => {
    if (Number.isFinite(value) && value > peak) peak = value;
  });
  const top = Math.max(1, Math.ceil(peak - 1e-9));
  const interval = niceIntegerStep(Math.ceil(top / 4));
  const max = Math.ceil(top / interval) * interval;
  return { min: 0, max, interval };
};

/** 只输出整数刻度。离整数远的浮点（含 3.3000000000000003）不显示。 */
export const formatIntegerTick = (value: number) => {
  if (!Number.isFinite(value)) return '';
  const nearest = Math.round(value);
  if (Math.abs(value - nearest) > 1e-6) return '';
  return String(nearest);
};

export const integerCountTicks = (bounds: IntegerCountAxis) => {
  const ticks: string[] = [];
  const steps = Math.round((bounds.max - bounds.min) / bounds.interval);
  for (let index = 0; index <= steps; index += 1) {
    ticks.push(formatIntegerTick(bounds.min + bounds.interval * index));
  }
  return ticks;
};
