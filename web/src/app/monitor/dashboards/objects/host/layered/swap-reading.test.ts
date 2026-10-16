import { describe, expect, it } from 'vitest';
import { formatSharedBytePair } from './readings';

const GiB = 1024 ** 3;
const MiB = 1024 ** 2;

describe('formatSharedBytePair', () => {
  it('shares one binary unit and keeps one decimal', () => {
    expect(formatSharedBytePair(1.2 * GiB, 4 * GiB)).toBe('1.2 / 4.0 GiB');
    expect(formatSharedBytePair(300 * MiB, 512 * MiB)).toBe('300.0 / 512.0 MiB');
  });

  it('falls back to the used side when total is missing', () => {
    expect(formatSharedBytePair(4 * GiB, null)).toBe('4GiB');
  });
});
