import { formatUnit } from "@/app/ops-analysis/utils/unitFormat";

interface FormatOptions {
  fallbackUnit?: string | null;
}

const RATE_UNIT_FACTORS: Record<string, number> = {
  bps: 1,
  Kbits: 1000,
  kbps: 1000,
  Kbps: 1000,
  Mbits: 1000 ** 2,
  Mbps: 1000 ** 2,
  Gbits: 1000 ** 3,
  Gbps: 1000 ** 3,
  Tbits: 1000 ** 4,
  Tbps: 1000 ** 4,
  Bps: 8,
  "byte/s": 8,
  KBs: 8 * 1000,
  MBs: 8 * 1000 ** 2,
  GBs: 8 * 1000 ** 3,
};

const normalizeUnit = (unit?: string | null): string => (unit ?? "").trim();

const formatWeOpsShortCount = (
  value: number | string | null | undefined,
): string => {
  const num = typeof value === "string" ? Number.parseFloat(value) : value;
  if (typeof num !== "number" || Number.isNaN(num)) return String(value ?? "--");
  const units = ["", " K", " Mil", " Bil", " Tri", " Quadr", " Quint", " Sext", " Sept"];
  let scaled = num;
  let index = 0;
  while (Math.abs(scaled) >= 1000 && index < units.length - 1) {
    scaled /= 1000;
    index += 1;
  }
  const text = (Math.round(scaled * 100) / 100).toFixed(2).replace(/\.?0+$/, "");
  return `${text}${units[index]}`;
};

export const formatNetworkMetricValue = (
  value: number | string | null | undefined,
  unit?: string | null,
  options: FormatOptions = {},
): string => {
  if (value === null || value === undefined || value === "") return "--";

  const resolvedUnit = normalizeUnit(unit) || normalizeUnit(options.fallbackUnit);
  if (!resolvedUnit || resolvedUnit === "none" || resolvedUnit === "NONE") {
    return formatWeOpsShortCount(value);
  }

  if (resolvedUnit === "bytes" || resolvedUnit === "decbytes") {
    return formatUnit(value, "bytesSI").text;
  }

  if (resolvedUnit === "percent" || resolvedUnit === "percentunit") {
    return formatUnit(value, resolvedUnit).text;
  }

  if (resolvedUnit === "ms") {
    return formatUnit(value, "ms").text;
  }

  const rateFactor = RATE_UNIT_FACTORS[resolvedUnit];
  if (rateFactor) {
    return formatUnit(value, "bps", { conversionFactor: rateFactor }).text;
  }

  return formatUnit(value, `custom:${resolvedUnit}`).text;
};
