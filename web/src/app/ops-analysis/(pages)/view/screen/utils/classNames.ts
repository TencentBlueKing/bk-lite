const weekDays = ["日", "一", "二", "三", "四", "五", "六"];

const pad2 = (value: number) => String(value).padStart(2, "0");

type ClockTranslate = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string>,
) => string;

export const formatScreenClock = (date: Date, t?: ClockTranslate) => {
  const weekday = t
    ? t(`opsAnalysis.screen.weekday${date.getDay()}`, weekDays[date.getDay()])
    : weekDays[date.getDay()];
  const values = {
    year: String(date.getFullYear()),
    month: pad2(date.getMonth() + 1),
    day: pad2(date.getDate()),
    weekday,
    hour: pad2(date.getHours()),
    minute: pad2(date.getMinutes()),
    second: pad2(date.getSeconds()),
  };
  if (!t) {
    return `${values.year}/${values.month}/${values.day} 周${weekday} ${values.hour}:${values.minute}:${values.second}`;
  }
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
