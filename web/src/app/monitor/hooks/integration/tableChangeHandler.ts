interface TableChangeHandler {
  type: 'simple' | 'combine' | 'option_field';
  target_field: string;
  source_fields?: string[];
  source_field?: string;
  separator?: string;
}

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
    const sourceValues = (handler.source_fields || []).map(
      (field) => row[field] || ''
    );
    return {
      ...row,
      [handler.target_field]: sourceValues.join(handler.separator || ':')
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
