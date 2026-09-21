import { describe, expect, it } from 'vitest';
import { classifyCredentialRefs } from '@/app/system-manager/utils/credentialRefs';

describe('classifyCredentialRefs', () => {
  it('treats missing inquiry as unknown dash', () => {
    expect(classifyCredentialRefs(null)).toEqual({ kind: 'unknown' });
    expect(classifyCredentialRefs('')).toEqual({ kind: 'unknown' });
  });

  it('treats confirmed empty refs as zero', () => {
    expect(classifyCredentialRefs([])).toEqual({ kind: 'zero' });
    expect(classifyCredentialRefs([{ module: 'cmdb', count: 0 }])).toEqual({ kind: 'zero' });
  });

  it('keeps positive chips from any module', () => {
    expect(classifyCredentialRefs([
      { module: 'cmdb', count: 2 },
      { module: 'monitor', count: 0 },
    ])).toEqual({
      kind: 'chips',
      items: [{ module: 'cmdb', count: 2 }],
    });
  });

  it('falls back to text for unexpected scalars', () => {
    expect(classifyCredentialRefs('CMDB 2')).toEqual({ kind: 'text', value: 'CMDB 2' });
    expect(classifyCredentialRefs(3)).toEqual({ kind: 'text', value: '3' });
  });
});
