export interface TableColumn {
  column_id: string;
  column_name?: string;
  column_type?: 'str' | 'number';
  order?: number;
  is_row_key?: boolean;
}

export interface ChangeRecordAttribute {
  attr_name?: string;
  attr_type?: string;
  option?: unknown;
}

export interface ChangeRecordSnapshotAttribute {
  attr_id?: string;
  attr_name?: string;
  attr_type?: string;
  columns?: TableColumn[];
}

export interface ChangeRecordAttributeSnapshot {
  version?: number;
  attributes?: Record<string, ChangeRecordSnapshotAttribute>;
}

export interface ChangeRecordDiffSource {
  label: string;
  before_data?: Record<string, unknown>;
  after_data?: Record<string, unknown>;
  attribute_snapshot?: ChangeRecordAttributeSnapshot;
}

export interface ChangeRecordDiffRow {
  attrId: string;
  attr: string;
  kind: 'scalar' | 'table';
  before: string;
  after: string;
  current: string;
  changed: boolean;
  currentDiff: boolean;
  table?: TableFieldDiff;
}

export type TableRowDiffStatus =
  | 'unchanged'
  | 'added'
  | 'removed'
  | 'modified'
  | 'moved'
  | 'ambiguous';

export interface TableCellDiff {
  columnId: string;
  columnName: string;
  before: string;
  after: string;
  current: string;
  changed: boolean;
  currentDiff: boolean;
}

export interface TableRowDiff {
  key: string;
  beforeIndex?: number;
  afterIndex?: number;
  currentIndex?: number;
  status: TableRowDiffStatus;
  cells: TableCellDiff[];
}

export interface TableFieldDiff {
  matchMode: 'position' | 'row-key' | 'row-level';
  rowKeyColumnId?: string;
  fallbackReason?: 'missing-row-key' | 'duplicate-row-key' | 'ambiguous-rows';
  rows: TableRowDiff[];
  summary: {
    addedRows: number;
    removedRows: number;
    modifiedRows: number;
    changedCells: number;
  };
}
