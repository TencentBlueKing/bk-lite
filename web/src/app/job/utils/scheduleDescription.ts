import type { useTranslation } from '@/utils/i18n';

type Translate = ReturnType<typeof useTranslation>['t'];

function numberInRange(field: string, min: number, max: number): number | undefined {
  if (!/^\d{1,2}$/.test(field)) return undefined;
  const value = Number(field);
  return value >= min && value <= max ? value : undefined;
}

function step(field: string, max: number): number | undefined {
  return field.startsWith('*/') ? numberInRange(field.slice(2), 1, max) : undefined;
}

export function describeCron(expression: string, t: Translate): string {
  if (!expression.trim()) return '-';
  const fields = expression.trim().split(/\s+/);
  if (fields.length !== 5) return t('job.scheduleCustom');

  const [minute, hour, day, month, weekday] = fields;
  const everyDay = day === '*' && month === '*' && weekday === '*';

  if (everyDay && hour === '*') {
    const interval = step(minute, 59);
    if (minute === '*' || interval === 1) return t('job.cronEveryMinute');
    if (interval !== undefined) {
      const key = 60 % interval === 0 ? 'job.scheduleMinuteInterval' : 'job.scheduleMinuteIntervalWithinHour';
      return t(key, undefined, { interval });
    }
  }

  const minuteValue = numberInRange(minute, 0, 59);
  if (minuteValue === undefined) return t('job.scheduleCustom');
  const minuteText = String(minuteValue).padStart(2, '0');

  if (everyDay) {
    const interval = hour === '*' ? 1 : step(hour, 23);
    if (interval === 1) {
      if (minuteValue === 0) return t('job.cronEveryHour');
      return t('job.scheduleHourlyAt', undefined, { minute: minuteValue });
    }
    if (interval !== undefined) {
      return t('job.scheduleHourInterval', undefined, { time: `00:${minuteText}`, interval });
    }
  }

  const hourValue = numberInRange(hour, 0, 23);
  if (hourValue === undefined || month !== '*') return t('job.scheduleCustom');
  const time = `${String(hourValue).padStart(2, '0')}:${minuteText}`;
  if (everyDay) return t('job.scheduleDaily', undefined, { time });

  if (day === '*') {
    if (weekday === '1-5') return t('job.scheduleWeekdays', undefined, { time });
    const weekdayValue = numberInRange(weekday, 0, 6);
    if (weekdayValue !== undefined) {
      return t('job.scheduleWeekly', undefined, { weekday: t(`job.scheduleWeekday.${weekdayValue}`), time });
    }
  }
  const dayValue = numberInRange(day, 1, 31);
  if (weekday === '*' && dayValue !== undefined) {
    return t('job.scheduleMonthly', undefined, { day: dayValue, time });
  }
  return t('job.scheduleCustom');
}
