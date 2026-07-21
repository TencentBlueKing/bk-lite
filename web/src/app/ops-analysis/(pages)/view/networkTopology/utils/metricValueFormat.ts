import { formatUnit } from "@/app/ops-analysis/utils/unitFormat";

interface FormatOptions {
  fallbackUnit?: string | null;
}

const IEC = 1024;
const SI = 1000;

const BIT_RATE_UNIT_FACTORS: Record<string, number> = {
  bps: 1,
  Kbits: 1000,
  kbits: 1000,
  kbps: 1000,
  Kbps: 1000,
  Mbits: 1000 ** 2,
  mbits: 1000 ** 2,
  Mbps: 1000 ** 2,
  mbps: 1000 ** 2,
  Gbits: 1000 ** 3,
  gbits: 1000 ** 3,
  Gbps: 1000 ** 3,
  gbps: 1000 ** 3,
  Tbits: 1000 ** 4,
  tbits: 1000 ** 4,
  Tbps: 1000 ** 4,
  tbps: 1000 ** 4,
  Pbits: 1000 ** 5,
  pbits: 1000 ** 5,
  Pbps: 1000 ** 5,
  pbps: 1000 ** 5,
};

const BYTE_RATE_UNIT_FACTORS: Record<string, number> = {
  Bps: 1,
  "byte/s": 1,
  Bytes: 1,
  KBs: SI,
  kBs: SI,
  MBs: SI ** 2,
  GBs: SI ** 3,
  TBs: SI ** 4,
  PBs: SI ** 5,
};

const IEC_BYTE_UNIT_FACTORS: Record<string, number> = {
  bytes: 1,
  kbytes: IEC,
  mbytes: IEC ** 2,
  gbytes: IEC ** 3,
  tbytes: IEC ** 4,
  pbytes: IEC ** 5,
};

const SI_BYTE_UNIT_FACTORS: Record<string, number> = {
  decbytes: 1,
  deckbytes: SI,
  decmbytes: SI ** 2,
  decgbytes: SI ** 3,
  dectbytes: SI ** 4,
  decpbytes: SI ** 5,
};

const IEC_BIT_UNIT_FACTORS: Record<string, number> = {
  bits: 1,
};

const SI_BIT_UNIT_FACTORS: Record<string, number> = {
  decbits: 1,
};

const TIME_UNIT_FACTORS_TO_MS: Record<string, number> = {
  ns: 1 / 1000 ** 2,
  "µs": 1 / 1000,
  us: 1 / 1000,
  ms: 1,
  s: 1000,
  m: 60 * 1000,
  min: 60 * 1000,
  h: 60 * 60 * 1000,
  d: 24 * 60 * 60 * 1000,
};

const normalizeUnit = (unit?: string | null): string => (unit ?? "").trim();

const toNumber = (value: number | string | null | undefined): number | null => {
  const num = typeof value === "string" ? Number.parseFloat(value) : value;
  return typeof num === "number" && !Number.isNaN(num) ? num : null;
};

const formatNumber = (num: number): string =>
  (Math.round(num * 100) / 100).toFixed(2).replace(/\.?0+$/, "") || "0";

const formatPrefixed = (
  value: number | string | null | undefined,
  conversionFactor: number,
  suffix: string,
  prefixes: Array<{ factor: number; prefix: string }>,
): string => {
  const num = toNumber(value);
  if (num === null) return String(value ?? "--");
  const scaledValue = num * conversionFactor;
  const step =
    prefixes.find((item) => Math.abs(scaledValue) >= item.factor) ??
    prefixes[prefixes.length - 1];
  return `${formatNumber(scaledValue / step.factor)} ${step.prefix}${suffix}`;
};

const formatDecimalPrefixed = (
  value: number | string | null | undefined,
  conversionFactor: number,
  suffix: string,
): string =>
  formatPrefixed(value, conversionFactor, suffix, [
    { factor: SI ** 5, prefix: "P" },
    { factor: SI ** 4, prefix: "T" },
    { factor: SI ** 3, prefix: "G" },
    { factor: SI ** 2, prefix: "M" },
    { factor: SI, prefix: "K" },
    { factor: 1, prefix: "" },
  ]);

const formatBinaryPrefixed = (
  value: number | string | null | undefined,
  conversionFactor: number,
  suffix: string,
): string =>
  formatPrefixed(value, conversionFactor, suffix, [
    { factor: IEC ** 5, prefix: "Pi" },
    { factor: IEC ** 4, prefix: "Ti" },
    { factor: IEC ** 3, prefix: "Gi" },
    { factor: IEC ** 2, prefix: "Mi" },
    { factor: IEC, prefix: "Ki" },
    { factor: 1, prefix: "" },
  ]);

const formatWeOpsShortCount = (
  value: number | string | null | undefined,
): string => {
  const num = toNumber(value);
  if (num === null) return String(value ?? "--");
  const units = [
    "",
    " K",
    " Mil",
    " Bil",
    " Tri",
    " Quadr",
    " Quint",
    " Sext",
    " Sept",
  ];
  let scaled = num;
  let index = 0;
  while (Math.abs(scaled) >= 1000 && index < units.length - 1) {
    scaled /= 1000;
    index += 1;
  }
  return `${formatNumber(scaled)}${units[index]}`;
};

export const formatNetworkMetricValue = (
  value: number | string | null | undefined,
  unit?: string | null,
  options: FormatOptions = {},
): string => {
  if (value === null || value === undefined || value === "") return "--";

  const resolvedUnit = normalizeUnit(unit) || normalizeUnit(options.fallbackUnit);
  if (
    !resolvedUnit ||
    resolvedUnit === "none" ||
    resolvedUnit === "NONE" ||
    resolvedUnit === "short"
  ) {
    return formatWeOpsShortCount(value);
  }

  const iecByteFactor = IEC_BYTE_UNIT_FACTORS[resolvedUnit];
  if (iecByteFactor) {
    return formatUnit(value, "bytesIEC", { conversionFactor: iecByteFactor }).text;
  }

  const siByteFactor = SI_BYTE_UNIT_FACTORS[resolvedUnit];
  if (siByteFactor) {
    return formatUnit(value, "bytesSI", { conversionFactor: siByteFactor }).text;
  }

  const iecBitFactor = IEC_BIT_UNIT_FACTORS[resolvedUnit];
  if (iecBitFactor) {
    return formatBinaryPrefixed(value, iecBitFactor, "b");
  }

  const siBitFactor = SI_BIT_UNIT_FACTORS[resolvedUnit];
  if (siBitFactor) {
    return formatDecimalPrefixed(value, siBitFactor, "b");
  }

  if (resolvedUnit === "percent" || resolvedUnit === "percentunit") {
    return formatUnit(value, resolvedUnit).text;
  }

  const timeFactor = TIME_UNIT_FACTORS_TO_MS[resolvedUnit];
  if (timeFactor) {
    return formatUnit(value, "ms", { conversionFactor: timeFactor }).text;
  }

  if (resolvedUnit === "pps") {
    return formatDecimalPrefixed(value, 1, "pps");
  }

  const byteRateFactor = BYTE_RATE_UNIT_FACTORS[resolvedUnit];
  if (byteRateFactor) {
    return formatDecimalPrefixed(value, byteRateFactor, "Bps");
  }

  const bitRateFactor = BIT_RATE_UNIT_FACTORS[resolvedUnit];
  if (bitRateFactor) {
    return formatUnit(value, "bps", { conversionFactor: bitRateFactor }).text;
  }

  return formatUnit(value, `custom:${resolvedUnit}`).text;
};
