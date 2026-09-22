export const INCIDENT_DETAIL_TRIGGER_COLUMN_KEYS = [
  'level',
  'title',
  'alert_count',
  'status',
  'duration',
] as const;

export const isIncidentDetailTriggerColumn = (key?: string | null) =>
  Boolean(key) &&
  (INCIDENT_DETAIL_TRIGGER_COLUMN_KEYS as readonly string[]).includes(key);

export const getIncidentDetailTriggerCellProps = <T,>(
  record: T,
  columnKey: string | undefined,
  onOpenDetail: (record: T) => void
) => {
  if (!isIncidentDetailTriggerColumn(columnKey)) return {};
  return {
    className: 'cursor-pointer',
    onClick: (event: { stopPropagation?: () => void }) => {
      event.stopPropagation?.();
      onOpenDetail(record);
    },
  };
};
