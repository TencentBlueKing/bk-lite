import {
  buildTableDiff,
  formatChangeRecordValue,
  getTableColumns,
  inferTableAttribute,
  valuesEqual,
} from './tableDiff';
import type {
  ChangeRecordAttribute,
  ChangeRecordDiffRow,
  ChangeRecordDiffSource,
} from './changeRecordTypes';

export type {
  ChangeRecordAttribute,
  ChangeRecordAttributeSnapshot,
  ChangeRecordDiffRow,
  ChangeRecordDiffSource,
  TableCellDiff,
  TableColumn,
  TableFieldDiff,
  TableRowDiff,
  TableRowDiffStatus,
} from './changeRecordTypes';

export const buildChangeRecordDiffRows = (
  selectedRecord: ChangeRecordDiffSource | null,
  currentInstance: Record<string, unknown>,
  attrFieldMap: Record<string, ChangeRecordAttribute>
): ChangeRecordDiffRow[] => {
  if (!selectedRecord || selectedRecord.label !== 'instance') return [];

  const beforeData = selectedRecord.before_data || {};
  const afterData = selectedRecord.after_data || {};
  const keys = Array.from(
    new Set([...Object.keys(afterData), ...Object.keys(beforeData)])
  ).filter((key) => !key.startsWith('_'));

  return keys.map((key) => {
    const snapshotAttribute = selectedRecord.attribute_snapshot?.attributes?.[key];
    const configuredAttribute: ChangeRecordAttribute | undefined = snapshotAttribute
      ? {
        attr_name: snapshotAttribute.attr_name,
        attr_type: snapshotAttribute.attr_type,
        option: snapshotAttribute.columns,
      }
      : attrFieldMap[key];
    const attribute = configuredAttribute || inferTableAttribute(
      beforeData[key],
      afterData[key],
      currentInstance[key]
    );
    const before = formatChangeRecordValue(beforeData[key], attribute);
    const after = formatChangeRecordValue(afterData[key], attribute);
    const current = formatChangeRecordValue(currentInstance[key], attribute);

    const table =
      attribute?.attr_type === 'table'
        ? buildTableDiff(
          beforeData[key],
          afterData[key],
          currentInstance[key],
          getTableColumns(attribute)
        )
        : undefined;

    return {
      attrId: key,
      attr: attribute?.attr_name || key,
      kind: table ? ('table' as const) : ('scalar' as const),
      before,
      after,
      current,
      changed: !valuesEqual(beforeData[key], afterData[key], attribute),
      currentDiff: !valuesEqual(afterData[key], currentInstance[key], attribute),
      table,
    };
  });
};
