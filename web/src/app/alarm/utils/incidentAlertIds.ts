import type { Key } from 'react';

const isFiniteNumber = (value: number): value is number => Number.isFinite(value);

export const toFiniteNumberIds = (keys: readonly Key[]): number[] =>
  keys
    .map((key) => {
      if (typeof key === 'number') return key;
      if (typeof key === 'bigint') return Number.NaN;
      return Number(key);
    })
    .filter(isFiniteNumber);
