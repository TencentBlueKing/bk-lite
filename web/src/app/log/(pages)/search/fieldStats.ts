const NON_AGGREGATABLE_FIELDS = new Set([
  'timestamp',
  '_time',
  '_stream',
  '_stream_id'
]);

export const getFieldStatsAttribute = (field: string) => field;

export const canExpandFieldStats = (field: string) =>
  !NON_AGGREGATABLE_FIELDS.has(field);
