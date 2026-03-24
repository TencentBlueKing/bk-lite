export type CronPresetKey =
  | 'custom'
  | 'every3Minutes'
  | 'every5Minutes'
  | 'every10Minutes'
  | 'every15Minutes'
  | 'every30Minutes'
  | 'hourly'
  | 'daily9am'
  | 'daily12pm'
  | 'daily6pm'
  | 'weekdays9am'
  | 'weekdays6pm'
  | 'monday9am'
  | 'friday6pm'
  | 'firstDay9am';

export const CUSTOM_PRESET: CronPresetKey = 'custom';

export const PRESET_CRONS: Record<Exclude<CronPresetKey, 'custom'>, string> = {
  every3Minutes: '*/3 * * * *',
  every5Minutes: '*/5 * * * *',
  every10Minutes: '*/10 * * * *',
  every15Minutes: '*/15 * * * *',
  every30Minutes: '*/30 * * * *',
  hourly: '0 * * * *',
  daily9am: '0 9 * * *',
  daily12pm: '0 12 * * *',
  daily6pm: '0 18 * * *',
  weekdays9am: '0 9 * * 1-5',
  weekdays6pm: '0 18 * * 1-5',
  monday9am: '0 9 * * 1',
  friday6pm: '0 18 * * 5',
  firstDay9am: '0 9 1 * *',
};

const formatHourMinute = (hour: string, minute: string) => {
  const normalizedMinute = minute.padStart(2, '0');
  const hourNumber = Number(hour);

  if (Number.isNaN(hourNumber)) {
    return `${hour}:${normalizedMinute}`;
  }

  return `${String(hourNumber).padStart(2, '0')}:${normalizedMinute}`;
};

const isNumberInRange = (value: string, min: number, max: number) => {
  if (!/^\d+$/.test(value)) {
    return false;
  }

  const numericValue = Number(value);
  return numericValue >= min && numericValue <= max;
};

const isValidStep = (value: string, min: number, max: number) => {
  if (!/^\*\/\d+$/.test(value)) {
    return false;
  }

  const step = Number(value.slice(2));
  return step >= 1 && step <= max - min + 1;
};

const isValidList = (value: string, min: number, max: number) => {
  return value.split(',').every((part) => isValidCronField(part, min, max));
};

const isValidRange = (value: string, min: number, max: number) => {
  if (!/^\d+-\d+$/.test(value)) {
    return false;
  }

  const [start, end] = value.split('-').map(Number);
  return start >= min && end <= max && start <= end;
};

const isValidCronField = (value: string, min: number, max: number) => {
  if (value === '*') {
    return true;
  }

  if (value.includes(',')) {
    return isValidList(value, min, max);
  }

  if (isValidStep(value, min, max)) {
    return true;
  }

  if (isValidRange(value, min, max)) {
    return true;
  }

  return isNumberInRange(value, min, max);
};

const getWeekdayLabel = (weekday: string, t: (key: string) => string) => {
  const weekdayMap: Record<string, string> = {
    '0': t('settings.correlation.cronDesc.weekdayNames.sunday'),
    '1': t('settings.correlation.cronDesc.weekdayNames.monday'),
    '2': t('settings.correlation.cronDesc.weekdayNames.tuesday'),
    '3': t('settings.correlation.cronDesc.weekdayNames.wednesday'),
    '4': t('settings.correlation.cronDesc.weekdayNames.thursday'),
    '5': t('settings.correlation.cronDesc.weekdayNames.friday'),
    '6': t('settings.correlation.cronDesc.weekdayNames.saturday'),
    '7': t('settings.correlation.cronDesc.weekdayNames.sunday'),
  };

  return weekdayMap[weekday] || weekday;
};

type CronFieldType = 'minute' | 'hour' | 'dayOfMonth' | 'month' | 'dayOfWeek';
type CronNodeType = 'enum' | 'range' | 'repeat' | 'rangeRepeat';

interface CronNode {
  type: CronNodeType;
  value?: string;
  min?: string;
  max?: string;
  repeatInterval?: string;
}

type CronAst = Record<CronFieldType, CronNode[]>;
type PrettyCronAst = Partial<Record<CronFieldType, CronNode[]>>;

const getCronListSeparator = (t: (key: string) => string) =>
  t('settings.correlation.cronDesc.listSeparator');

const getCronListConjunction = (t: (key: string) => string) =>
  t('settings.correlation.cronDesc.listConjunction');

const parseCronField = (expression: string): CronNode[] => {
  return expression
    .trim()
    .split(',')
    .filter(Boolean)
    .map((atom) => {
      if (atom.includes('-') && atom.includes('/')) {
        const [range, repeatInterval] = atom.split('/');
        const [min, max] = range.split('-');
        return {
          type: 'rangeRepeat',
          min,
          max,
          repeatInterval,
        } satisfies CronNode;
      }

      if (atom.includes('/')) {
        const [value, repeatInterval] = atom.split('/');
        return {
          type: 'repeat',
          value,
          repeatInterval,
        } satisfies CronNode;
      }

      if (atom.includes('-')) {
        const [min, max] = atom.split('-');
        return {
          type: 'range',
          min,
          max,
        } satisfies CronNode;
      }

      return {
        type: 'enum',
        value: atom,
      } satisfies CronNode;
    });
};

const isAllValue = (nodes?: CronNode[]) =>
  !!nodes
  && nodes.length === 1
  && nodes[0].type === 'enum'
  && (nodes[0].value === '*' || nodes[0].value === '?');

const optimizeCronAst = (fieldMap: CronAst): PrettyCronAst => {
  const prettyMap: PrettyCronAst = {};

  prettyMap.month = isAllValue(fieldMap.month) ? [] : fieldMap.month;

  if (isAllValue(fieldMap.dayOfMonth) && isAllValue(fieldMap.month) && isAllValue(fieldMap.dayOfWeek)) {
    prettyMap.dayOfMonth = [];
    delete prettyMap.month;
  } else {
    if (!isAllValue(fieldMap.dayOfWeek)) {
      prettyMap.dayOfWeek = fieldMap.dayOfWeek;
    }
    if (!isAllValue(fieldMap.dayOfMonth)) {
      prettyMap.dayOfMonth = fieldMap.dayOfMonth;
    }
    if (!prettyMap.dayOfMonth && !prettyMap.dayOfWeek && (prettyMap.month?.length ?? 0) > 0) {
      prettyMap.dayOfMonth = [];
    }
  }

  prettyMap.hour = isAllValue(fieldMap.hour) ? [] : fieldMap.hour;
  if ((prettyMap.hour?.length ?? 0) < 1 && prettyMap.dayOfMonth && prettyMap.dayOfMonth.length < 1) {
    delete prettyMap.dayOfMonth;
  }

  prettyMap.minute = isAllValue(fieldMap.minute) ? [] : fieldMap.minute;
  if ((prettyMap.minute?.length ?? 0) < 1 && (prettyMap.hour?.length ?? 0) < 1) {
    delete prettyMap.hour;
  }

  if ((prettyMap.dayOfMonth?.length ?? 0) > 0 || (prettyMap.dayOfWeek?.length ?? 0) > 0) {
    if ((prettyMap.month?.length ?? 0) < 1) {
      delete prettyMap.month;
    }
  }

  return prettyMap;
};

const getWeekdayShortLabel = (weekday: string, t: (key: string) => string) => {
  const label = getWeekdayLabel(weekday, t);
  return label.startsWith('周') ? label.slice(1) : label;
};

const formatFieldValue = (
  field: CronFieldType,
  value: string,
  t: (key: string) => string
) => {
  switch (field) {
    case 'minute':
      return value.padStart(2, '0');
    case 'hour':
      return value.padStart(2, '0');
    case 'dayOfMonth':
    case 'month':
      return `${Number(value)}`;
    case 'dayOfWeek':
      return getWeekdayShortLabel(value, t);
    default:
      return value;
  }
};

const joinDescriptions = (items: string[], t: (key: string) => string) => {
  if (items.length < 2) {
    return items.join('');
  }

  const pre = items.slice(0, -1);
  const last = items[items.length - 1];
  return `${pre.join(getCronListSeparator(t))}${getCronListConjunction(t)}${last}`;
};

const translateCronNode = (
  field: CronFieldType,
  node: CronNode,
  t: (key: string) => string
) => {
  const keyBase = `settings.correlation.cronDesc.fields.${field}`;

  switch (node.type) {
    case 'enum':
      return t(`${keyBase}.value`).replace(
        '{value}',
        formatFieldValue(field, node.value || '', t)
      );
    case 'range':
      return t(`${keyBase}.range`)
        .replace('{start}', formatFieldValue(field, node.min || '', t))
        .replace('{end}', formatFieldValue(field, node.max || '', t));
    case 'repeat':
      if (node.value === '*') {
        return t(`${keyBase}.everyN`).replace('{interval}', node.repeatInterval || '');
      }
      return t(`${keyBase}.repeatFrom`)
        .replace('{value}', formatFieldValue(field, node.value || '', t))
        .replace('{interval}', node.repeatInterval || '');
    case 'rangeRepeat':
      return t(`${keyBase}.rangeRepeat`)
        .replace('{start}', formatFieldValue(field, node.min || '', t))
        .replace('{end}', formatFieldValue(field, node.max || '', t))
        .replace('{interval}', node.repeatInterval || '');
    default:
      return '';
  }
};

const translateCronField = (
  ast: PrettyCronAst,
  field: CronFieldType,
  t: (key: string) => string
) => {
  if (!Object.prototype.hasOwnProperty.call(ast, field)) {
    return '';
  }

  const sequence = ast[field] || [];
  if (sequence.length < 1) {
    return t(`settings.correlation.cronDesc.fields.${field}.any`);
  }

  return joinDescriptions(
    sequence.map((node) => translateCronNode(field, node, t)),
    t
  );
};

const buildCronAst = (
  minute: string,
  hour: string,
  dayOfMonth: string,
  month: string,
  dayOfWeek: string
): CronAst => ({
  minute: parseCronField(minute),
  hour: parseCronField(hour),
  dayOfMonth: parseCronField(dayOfMonth),
  month: parseCronField(month),
  dayOfWeek: parseCronField(dayOfWeek),
});

const buildGenericCronDescription = (
  minute: string,
  hour: string,
  dayOfMonth: string,
  month: string,
  dayOfWeek: string,
  t: (key: string) => string
) => {
  const ast = optimizeCronAst(buildCronAst(minute, hour, dayOfMonth, month, dayOfWeek));
  const dateDescriptions = [
    translateCronField(ast, 'month', t),
    translateCronField(ast, 'dayOfMonth', t),
    translateCronField(ast, 'dayOfWeek', t),
  ].filter(Boolean);

  const timeDescriptions = [
    translateCronField(ast, 'hour', t),
    translateCronField(ast, 'minute', t),
  ].filter(Boolean);

  const descriptions = [...dateDescriptions];
  if (timeDescriptions.length > 0) {
    const mergedTime = timeDescriptions.join(' ')
      .replace(/(\d{2}) 时 (\d{2}) 分$/, '$1:$2')
      .replace(/每小时 00 分$/, '整点');
    descriptions.push(mergedTime);
  }

  return descriptions.join(' ');
};

export const getCronDescription = (cron: string, t: (key: string) => string): string => {
  const trimmed = cron.trim();

  if (!trimmed) {
    return '';
  }

  const parts = trimmed.split(/\s+/);
  if (parts.length !== 5) {
    return t('settings.correlation.cronDesc.invalid');
  }

  const [minute, hour, day, month, week] = parts;

  if (
    !isValidCronField(minute, 0, 59)
    || !isValidCronField(hour, 0, 23)
    || !isValidCronField(day, 1, 31)
    || !isValidCronField(month, 1, 12)
    || !isValidCronField(week, 0, 7)
  ) {
    return t('settings.correlation.cronDesc.invalid');
  }

  if (minute === '*' && hour === '*' && day === '*' && month === '*' && week === '*') {
    return t('settings.correlation.cronDesc.everyMinute');
  }

  if (/^\*\/\d+$/.test(minute) && hour === '*' && day === '*' && month === '*' && week === '*') {
    return t('settings.correlation.cronDesc.everyNMinutes').replace(
      '{interval}',
      minute.replace('*/', '')
    );
  }

  if (minute === '0' && /^\*\/\d+$/.test(hour) && day === '*' && month === '*' && week === '*') {
    return t('settings.correlation.cronDesc.everyNHours').replace(
      '{interval}',
      hour.replace('*/', '')
    );
  }

  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === '*' && month === '*' && week === '*') {
    return t('settings.correlation.cronDesc.dailyAt').replace(
      '{time}',
      formatHourMinute(hour, minute)
    );
  }

  if (
    /^\d+$/.test(minute) &&
    /^\d+$/.test(hour) &&
    day === '*' &&
    month === '*' &&
    week === '1-5'
  ) {
    return t('settings.correlation.cronDesc.weekdaysAt').replace(
      '{time}',
      formatHourMinute(hour, minute)
    );
  }

  if (
    /^\d+$/.test(minute) &&
    /^\d+$/.test(hour) &&
    day === '*' &&
    month === '*' &&
    /^\d+$/.test(week)
  ) {
    return t('settings.correlation.cronDesc.weeklyAt')
      .replace('{weekday}', getWeekdayLabel(week, t))
      .replace('{time}', formatHourMinute(hour, minute));
  }

  if (
    /^\d+$/.test(minute) &&
    /^\d+$/.test(hour) &&
    /^\d+$/.test(day) &&
    month === '*' &&
    week === '*'
  ) {
    return t('settings.correlation.cronDesc.monthlyAt')
      .replace('{day}', day)
      .replace('{time}', formatHourMinute(hour, minute));
  }

  return buildGenericCronDescription(minute, hour, day, month, week, t);
};

export const isValidCronExpression = (cron?: string): boolean => {
  if (!cron?.trim()) {
    return false;
  }

  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) {
    return false;
  }

  const [minute, hour, day, month, week] = parts;

  return (
    isValidCronField(minute, 0, 59)
    && isValidCronField(hour, 0, 23)
    && isValidCronField(day, 1, 31)
    && isValidCronField(month, 1, 12)
    && isValidCronField(week, 0, 7)
  );
};
