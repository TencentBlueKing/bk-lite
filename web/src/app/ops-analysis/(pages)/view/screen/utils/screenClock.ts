import type { ScreenClockFormatId } from '@/app/ops-analysis/types/screen';

const weekDays = ['日', '一', '二', '三', '四', '五', '六'];

const pad2 = (value: number) => String(value).padStart(2, '0');

export interface ScreenClockDisplayParts {
  date?: string;
  week?: string;
  primary: string;
}

export const getScreenClockDisplayParts = (
  date: Date,
  format: ScreenClockFormatId = 'YYYY-MM-DD HH:mm:ss',
): ScreenClockDisplayParts => {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = pad2(date.getHours());
  const minutes = pad2(date.getMinutes());
  const seconds = pad2(date.getSeconds());

  switch (format) {
    case 'HH:mm:ss':
      return { primary: `${hours}:${minutes}:${seconds}` };
    case 'YYYY-MM-DD':
      return { primary: `${year}-${pad2(month)}-${pad2(day)}` };
    case 'YYYY年M月D日':
      return { primary: `${year}年${month}月${day}日` };
    case 'M月D日 HH:mm':
      return { date: `${month}月${day}日`, primary: `${hours}:${minutes}` };
    case 'dddd HH:mm:ss':
      return {
        date: `${year}.${pad2(month)}.${pad2(day)}`,
        week: `星期${weekDays[date.getDay()]}`,
        primary: `${hours}:${minutes}:${seconds}`,
      };
    default:
      return {
        date: `${year}-${pad2(month)}-${pad2(day)}`,
        primary: `${hours}:${minutes}:${seconds}`,
      };
  }
};

export const formatScreenClockByPreset = (
  date: Date,
  format: ScreenClockFormatId = 'YYYY-MM-DD HH:mm:ss',
) => {
  const year = date.getFullYear();
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hours = pad2(date.getHours());
  const minutes = pad2(date.getMinutes());
  const seconds = pad2(date.getSeconds());

  switch (format) {
    case 'HH:mm:ss':
      return `${hours}:${minutes}:${seconds}`;
    case 'YYYY-MM-DD':
      return `${year}-${pad2(month)}-${pad2(day)}`;
    case 'YYYY年M月D日':
      return `${year}年${month}月${day}日`;
    case 'M月D日 HH:mm':
      return `${month}月${day}日 ${hours}:${minutes}`;
    case 'dddd HH:mm:ss':
      return `${year}-${pad2(month)}-${pad2(day)} 星期${weekDays[date.getDay()]} ${hours}:${minutes}:${seconds}`;
    default:
      return `${year}-${pad2(month)}-${pad2(day)} ${hours}:${minutes}:${seconds}`;
  }
};
