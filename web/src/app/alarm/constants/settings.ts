export const initialConditionLists: Record<
  string,
  { name: string; desc: string }[]
> = {
  title: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 're', desc: '正则' },
    { name: 'not_contains', desc: '不包含' },
  ],
  source_id: [{ name: 'eq', desc: '等于' }],
  level: [{ name: 'eq', desc: '等于' }],
  resource_type: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 'ne', desc: '不等于' },
  ],
  resource_id: [
    { name: 'eq', desc: '等于' },
    { name: 'contains', desc: '包含' },
    { name: 're', desc: '正则' },
    { name: 'not_contains', desc: '不包含' },
  ],
  content: [
    { name: 'contains', desc: '包含' },
    { name: 're', desc: '正则' },
    { name: 'not_contains', desc: '不包含' },
  ],
};

export const ruleList = [
  {
    name: 'title',
    verbose_name: '标题',
  },
  {
    name: 'source_id',
    verbose_name: '告警源',
  },
  { name: 'level', verbose_name: '级别' },
  { name: 'resource_type', verbose_name: '类型对象' },
  { name: 'resource_id', verbose_name: '对象实例' },
  { name: 'content', verbose_name: '内容' },
];

export const typeLabel: Record<string, string> = {
  one: '单次',
  day: '每天',
  week: '每周',
  month: '每月',
};

export const weekMap: string[] = [
  '',
  '星期一',
  '星期二',
  '星期三',
  '星期四',
  '星期五',
  '星期六',
  '星期天',
];

export const timeInterval = [
  { name: '单次', value: 'one' },
  { name: '每天', value: 'day' },
  { name: '每周', value: 'week' },
  { name: '每月', value: 'month' },
];

export const weekList = [
  { name: '星期一', value: 1 },
  { name: '星期二', value: 2 },
  { name: '星期三', value: 3 },
  { name: '星期四', value: 4 },
  { name: '星期五', value: 5 },
  { name: '星期六', value: 6 },
  { name: '星期天', value: 7 },
];
