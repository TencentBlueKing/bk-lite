const FIELD_STATS_ATTRIBUTE_MAP: Record<string, string> = {
  message: '_msg'
};

const NON_AGGREGATABLE_FIELDS = new Set([
  'timestamp',
  '_time',
  '_stream',
  '_stream_id'
]);

export const getFieldStatsAttribute = (field: string) =>
  FIELD_STATS_ATTRIBUTE_MAP[field] || field;

export const canExpandFieldStats = (field: string) =>
  !NON_AGGREGATABLE_FIELDS.has(field);
