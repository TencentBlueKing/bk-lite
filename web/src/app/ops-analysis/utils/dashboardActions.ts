export const OPERATION_COLUMN_KEY_PREFIX = '__actions__';

export const createOperationColumnKey = (
  columns: Array<{ key?: string }>,
): string => {
  const existingKeys = new Set(
    columns.map((column) => column.key).filter(Boolean),
  );

  if (!existingKeys.has(OPERATION_COLUMN_KEY_PREFIX)) {
    return OPERATION_COLUMN_KEY_PREFIX;
  }

  let index = 2;
  while (existingKeys.has(`__actions_${index}__`)) {
    index += 1;
  }

  return `__actions_${index}__`;
};
