interface TableChangeHandler {
  type: 'simple' | 'combine' | 'option_field' | 'option_then_combine';
  target_field: string;
  source_fields?: string[];
  source_field?: string;
  stash_field?: string;
  separator?: string;
}

const combineSourceFields = (
  row: Record<string, any>,
  sourceFields: string[] | undefined,
  separator: string
): string =>
  (sourceFields || [])
    .map((field) => {
      const value = row[field];
      if (value === undefined || value === null) return '';
      return String(value).trim();
    })
    .filter(Boolean)
    .join(separator);

export const applyTableChangeHandler = (
  row: Record<string, any>,
  value: any,
  options: Record<string, any>[],
  handler?: TableChangeHandler
): Record<string, any> => {
  if (!handler) return row;

  if (handler.type === 'simple') {
    const sourceValue = handler.source_fields?.[0]
      ? row[handler.source_fields[0]]
      : value;
    return { ...row, [handler.target_field]: sourceValue };
  }

  if (handler.type === 'combine') {
    return {
      ...row,
      [handler.target_field]: combineSourceFields(
        row,
        handler.source_fields,
        handler.separator || ':'
      ),
    };
  }

  if (handler.type === 'option_then_combine') {
    const option = options.find((item) => item.value === value);
    const optionValue = handler.source_field
      ? option?.[handler.source_field]
      : undefined;
    if (
      optionValue === undefined ||
      optionValue === null ||
      optionValue === ''
    ) {
      return row;
    }
    const stashField = handler.stash_field;
    if (!stashField) {
      return row;
    }
    const nextRow = { ...row, [stashField]: optionValue };
    return {
      ...nextRow,
      [handler.target_field]: combineSourceFields(
        nextRow,
        handler.source_fields,
        handler.separator || '-'
      ),
    };
  }

  const option = options.find((item) => item.value === value);
  const sourceValue = handler.source_field
    ? option?.[handler.source_field]
    : undefined;
  if (
    sourceValue === undefined ||
    sourceValue === null ||
    sourceValue === ''
  ) {
    return row;
  }
  return { ...row, [handler.target_field]: sourceValue };
};
