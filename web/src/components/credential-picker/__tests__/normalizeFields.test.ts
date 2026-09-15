import { describe, expect, it } from 'vitest';
import { normalizeCredentialFieldValues } from '../normalizeFields';
import type { CredentialFieldSchema } from '../types';

const SSH: CredentialFieldSchema[] = [
  { id: 'username', name: '用户名', kind: 'string', required: true },
  { id: 'private_key', name: '私钥内容', kind: 'secret', required: true },
  { id: 'passphrase', name: '私钥口令', kind: 'secret' },
];

describe('normalizeCredentialFieldValues', () => {
  it('omits a blank optional secret so edit can keep the stored value', () => {
    expect(
      normalizeCredentialFieldValues(SSH, {
        username: 'ops',
        private_key: '',
        passphrase: '',
      }),
    ).toEqual({ username: 'ops', private_key: '' });
  });

  it('keeps a typed optional secret', () => {
    expect(
      normalizeCredentialFieldValues(SSH, {
        username: 'ops',
        private_key: '',
        passphrase: 'typed',
      }),
    ).toEqual({ username: 'ops', private_key: '', passphrase: 'typed' });
  });
});
