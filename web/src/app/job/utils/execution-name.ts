const pad = (value: number, length = 2) => String(value).padStart(length, '0');

export const createDefaultExecutionName = (prefix: string, now = new Date()) => (
  `${prefix}${now.getFullYear()}`
  + `${pad(now.getMonth() + 1)}`
  + `${pad(now.getDate())}`
  + `${pad(now.getHours())}`
  + `${pad(now.getMinutes())}`
  + `${pad(now.getSeconds())}`
  + `${pad(now.getMilliseconds(), 3)}`
);
