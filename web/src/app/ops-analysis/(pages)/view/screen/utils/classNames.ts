const pad2 = (value: number) => String(value).padStart(2, "0");

type ClockTranslate = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string>,
) => string;

const formatClockFallback: ClockTranslate = (id, defaultMessage, values) => {
  const template = defaultMessage ?? id;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
};

const weekdayLabel = (day: number, t: ClockTranslate) => {
  switch (day) {
    case 0:
      return t("opsAnalysis.screen.weekday0", "日");
    case 1:
      return t("opsAnalysis.screen.weekday1", "一");
    case 2:
      return t("opsAnalysis.screen.weekday2", "二");
    case 3:
      return t("opsAnalysis.screen.weekday3", "三");
    case 4:
      return t("opsAnalysis.screen.weekday4", "四");
    case 5:
      return t("opsAnalysis.screen.weekday5", "五");
    case 6:
      return t("opsAnalysis.screen.weekday6", "六");
    default:
      return t("opsAnalysis.screen.weekday0", "日");
  }
};

export const formatScreenClock = (date: Date, translate?: ClockTranslate) => {
  const t: ClockTranslate = translate ?? formatClockFallback;
  const values = {
    year: String(date.getFullYear()),
    month: pad2(date.getMonth() + 1),
    day: pad2(date.getDate()),
    weekday: weekdayLabel(date.getDay(), t),
    hour: pad2(date.getHours()),
    minute: pad2(date.getMinutes()),
    second: pad2(date.getSeconds()),
  };
  return t(
    "opsAnalysis.screen.clock",
    "{year}/{month}/{day} 周{weekday} {hour}:{minute}:{second}",
    values,
  );
};

export const getScreenRndNodeClassName = (selected: boolean) =>
  ["screen-rnd-node", selected ? "screen-rnd-node--selected" : ""]
    .filter(Boolean)
    .join(" ");
