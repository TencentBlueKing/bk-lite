export type ParamInputChangeValue = string | number | null;

export const normalizeParamInputChangeValue = (
  valueOrEvent: unknown,
): ParamInputChangeValue => {
  if (
    typeof valueOrEvent === 'object' &&
    valueOrEvent !== null &&
    'target' in valueOrEvent
  ) {
    const target = valueOrEvent.target;
    if (
      typeof target === 'object' &&
      target !== null &&
      'value' in target &&
      (typeof target.value === 'string' || typeof target.value === 'number')
    ) {
      return target.value;
    }
  }

  if (valueOrEvent === null) {
    return null;
  }

  if (
    typeof valueOrEvent === 'string' ||
    typeof valueOrEvent === 'number'
  ) {
    return valueOrEvent;
  }

  return null;
};
