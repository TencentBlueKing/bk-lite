export interface FormFieldDependency {
  field?: string | string[];
  value?: unknown;
  includes?: unknown;
  conditions?: Array<Array<{ equals?: unknown; in?: unknown[] }>>;
}

type GetFieldValue = (field: string) => unknown;

const asList = (value: unknown): unknown[] => {
  if (Array.isArray(value)) return value;
  if (value === undefined || value === null || value === '') return [];
  return [value];
};

/**
 * Evaluate UI.json dependency rules for form fields / table columns.
 * Supports:
 * - `{ field, value }` exact match
 * - `{ field, includes }` array/string contains
 * - `{ field: string[], conditions }` multi-field AND with equals/in
 */
export const isDependencySatisfied = (
  dependency: FormFieldDependency | null | undefined,
  getFieldValue: GetFieldValue
): boolean => {
  if (!dependency?.field) return true;

  const { field, value, includes, conditions } = dependency;

  if (typeof field === 'string') {
    const watchValue = getFieldValue(field);
    if (includes !== undefined) {
      return asList(watchValue).some((item) => item === includes);
    }
    if (value !== undefined) {
      return watchValue === value;
    }
    return true;
  }

  if (Array.isArray(field)) {
    return field.every((name, index) => {
      const watchValue = getFieldValue(name);
      const fieldConditions = conditions?.[index] || [];
      if (!fieldConditions.length) return true;
      return fieldConditions.some((condition) => {
        if (condition.equals !== undefined) {
          return watchValue === condition.equals;
        }
        if (condition.in !== undefined) {
          return condition.in.includes(watchValue as never);
        }
        return false;
      });
    });
  }

  return true;
};

export const filterColumnsByDependency = <T extends { dependency?: FormFieldDependency }>(
  columns: T[] | null | undefined,
  getFieldValue: GetFieldValue
): T[] => {
  if (!columns?.length) return [];
  return columns.filter((column) =>
    isDependencySatisfied(column.dependency, getFieldValue)
  );
};

export const collectDependencyFieldNames = (
  columns: Array<{ dependency?: FormFieldDependency }> | null | undefined
): string[] => {
  const fields = new Set<string>();
  for (const column of columns || []) {
    const field = column.dependency?.field;
    if (typeof field === 'string') {
      fields.add(field);
    } else if (Array.isArray(field)) {
      field.forEach((name) => fields.add(name));
    }
  }
  return Array.from(fields);
};
