import dayjs from 'dayjs';

export const formatCollectReportTime = (lastTime: string) => {
  const trimmed = String(lastTime).trim();
  if (/^\d+$/.test(trimmed)) {
    const value = Number(trimmed);
    const millis = value >= 1e12 ? value : value * 1000;
    return dayjs(millis).format('YYYY-MM-DD HH:mm:ss');
  }
  return dayjs(trimmed).format('YYYY-MM-DD HH:mm:ss');
};
