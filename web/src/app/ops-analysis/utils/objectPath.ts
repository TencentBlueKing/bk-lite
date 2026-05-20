export const getValueByPath = (obj: unknown, path?: string): unknown => {
  if (!obj || !path) return undefined;

  return path.split('.').reduce((current, key) => {
    if (current === null || current === undefined) return undefined;

    if (Array.isArray(current)) {
      const index = parseInt(key, 10);
      if (!Number.isNaN(index) && index >= 0 && index < current.length) {
        return current[index];
      }

      return current.length > 0 && current[0] && typeof current[0] === 'object'
        ? (current[0] as Record<string, unknown>)[key]
        : undefined;
    }

    return (current as Record<string, unknown>)[key];
  }, obj);
};
