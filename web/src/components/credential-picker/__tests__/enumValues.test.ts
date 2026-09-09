import { describe, expect, it } from 'vitest';
import { parseEnumValues } from '../enumValues';

describe('parseEnumValues', () => {
  it('splits English commas in an input string and trims spaces', () => {
    expect(parseEnumValues('1, 2')).toEqual(['1', '2']);
    expect(parseEnumValues('v2c,v3')).toEqual(['v2c', 'v3']);
  });

  it('treats Chinese commas and enumeration commas as part of the value', () => {
    expect(parseEnumValues('1，2')).toEqual(['1，2']);
    expect(parseEnumValues('1、2')).toEqual(['1、2']);
  });

  it('keeps stored array tokens as-is, even if a token contains a comma', () => {
    expect(parseEnumValues(['1, 2'])).toEqual(['1, 2']);
    expect(parseEnumValues(['1', '2'])).toEqual(['1', '2']);
  });

  it('drops empties and duplicates', () => {
    expect(parseEnumValues('a, , a, b')).toEqual(['a', 'b']);
    expect(parseEnumValues(['a', '', 'a', 'b'])).toEqual(['a', 'b']);
    expect(parseEnumValues('')).toEqual([]);
  });
});
