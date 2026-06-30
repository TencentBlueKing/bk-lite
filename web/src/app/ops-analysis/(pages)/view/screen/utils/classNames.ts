const weekDays = ["日", "一", "二", "三", "四", "五", "六"];

const pad2 = (value: number) => String(value).padStart(2, "0");

export const formatScreenClock = (date: Date) =>
  `${date.getFullYear()}/${pad2(date.getMonth() + 1)}/${pad2(date.getDate())} 周${weekDays[date.getDay()]} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;

export const getScreenRndNodeClassName = (selected: boolean) =>
  ["screen-rnd-node", selected ? "screen-rnd-node--selected" : ""]
    .filter(Boolean)
    .join(" ");
