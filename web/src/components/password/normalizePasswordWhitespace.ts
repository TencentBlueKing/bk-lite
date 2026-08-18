export interface PasswordWhitespaceNormalizationResult {
  value: string;
  changed: boolean;
}

export interface PasswordFieldDefinition {
  name?: unknown;
  type?: unknown;
  editable?: unknown;
}

export interface PasswordFieldsNormalizationResult<
  T extends Record<string, unknown>,
> {
  values: T;
  changedFields: string[];
}

export const normalizePasswordWhitespace = (
  value: string,
): PasswordWhitespaceNormalizationResult => {
  const normalizedValue = value.trim();
  return {
    value: normalizedValue,
    changed: normalizedValue !== value,
  };
};

export const normalizePasswordFields = <T extends Record<string, unknown>>(
  values: T,
  fields: readonly PasswordFieldDefinition[] | undefined,
  options: { includeReadOnly?: boolean } = {},
): PasswordFieldsNormalizationResult<T> => {
  let normalizedValues = values;
  const changedFields: string[] = [];

  (fields || []).forEach((field) => {
    if (
      field.type !== 'password' ||
      typeof field.name !== 'string' ||
      (!options.includeReadOnly && field.editable === false)
    ) {
      return;
    }

    const currentValue = normalizedValues[field.name];
    if (typeof currentValue !== 'string') {
      return;
    }

    const result = normalizePasswordWhitespace(currentValue);
    if (!result.changed) {
      return;
    }

    const writableValues: Record<string, unknown> =
      normalizedValues === values
        ? { ...values }
        : (normalizedValues as Record<string, unknown>);
    writableValues[field.name] = result.value;
    normalizedValues = writableValues as T;
    changedFields.push(field.name);
  });

  return {
    values: normalizedValues,
    changedFields,
  };
};
