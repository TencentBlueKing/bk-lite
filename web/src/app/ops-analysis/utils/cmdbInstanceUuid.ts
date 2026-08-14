const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export const isValidCmdbInstanceUuid = (value: unknown): value is string =>
  typeof value === 'string' && UUID_PATTERN.test(value);
