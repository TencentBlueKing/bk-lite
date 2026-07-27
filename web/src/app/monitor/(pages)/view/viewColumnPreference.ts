export interface ViewColumnLike {
  key: string;
}

export interface ResolvedViewColumns<T extends ViewColumnLike> {
  columns: T[];
  fieldKeys: string[];
}

export const resolveViewColumns = <T extends ViewColumnLike>(
  availableColumns: T[],
  savedFieldKeys: string[] | null | undefined,
  fixedFieldKeys: string[] = ['action']
): ResolvedViewColumns<T> => {
  const fixedKeys = new Set(fixedFieldKeys);
  const choosableColumns = availableColumns.filter(
    (column) => !fixedKeys.has(column.key)
  );
  const availableByKey = new Map(
    choosableColumns.map((column) => [column.key, column])
  );
  const validSavedKeys = (savedFieldKeys || []).filter((key) =>
    availableByKey.has(key)
  );
  const fieldKeys = validSavedKeys.length
    ? validSavedKeys
    : choosableColumns.map((column) => column.key);
  const selectedColumns = fieldKeys
    .map((key) => availableByKey.get(key))
    .filter((column): column is T => Boolean(column));
  const fixedColumns = availableColumns.filter((column) =>
    fixedKeys.has(column.key)
  );

  return {
    columns: [...selectedColumns, ...fixedColumns],
    fieldKeys,
  };
};
