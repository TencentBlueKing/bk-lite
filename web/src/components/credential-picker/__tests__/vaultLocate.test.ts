import { describe, expect, it } from 'vitest';
import { CREDENTIAL_CATEGORIES, CREDENTIAL_MENU_PATH } from '../types';
import { buildCredentialVaultUrl, resolveCredentialLocate } from '../vaultLocate';

const MYSQL = { key: 'mysql', categories: ['database'] };
const SSH = { key: 'ssh', categories: ['host'] };
const CUSTOM = { key: 'vault', categories: ['secret-store'] };

describe('buildCredentialVaultUrl', () => {
  it('keeps the bare vault path when category is missing', () => {
    expect(buildCredentialVaultUrl()).toBe(CREDENTIAL_MENU_PATH);
    expect(buildCredentialVaultUrl(undefined, 'mysql')).toBe(CREDENTIAL_MENU_PATH);
    expect(buildCredentialVaultUrl('', 'mysql')).toBe(CREDENTIAL_MENU_PATH);
  });

  it('appends category only, or category and type together', () => {
    expect(buildCredentialVaultUrl('database')).toBe(
      `${CREDENTIAL_MENU_PATH}?category=database`,
    );
    expect(buildCredentialVaultUrl('database', 'mysql')).toBe(
      `${CREDENTIAL_MENU_PATH}?category=database&type=mysql`,
    );
  });
});

describe('resolveCredentialLocate', () => {
  it('falls back to the default category when query has no category', () => {
    expect(resolveCredentialLocate({}, [MYSQL, SSH])).toEqual({
      category: CREDENTIAL_CATEGORIES[0],
    });
    expect(resolveCredentialLocate({ type: 'mysql' }, [MYSQL, SSH])).toEqual({
      category: CREDENTIAL_CATEGORIES[0],
    });
  });

  it('selects a known category and type, and keeps all-types when type is absent', () => {
    expect(resolveCredentialLocate({ category: 'database' }, [MYSQL, SSH])).toEqual({
      category: 'database',
    });
    expect(
      resolveCredentialLocate({ category: 'database', type: 'mysql' }, [MYSQL, SSH]),
    ).toEqual({ category: 'database', type: 'mysql' });
  });

  it('silently drops invalid category or type', () => {
    expect(
      resolveCredentialLocate({ category: 'nope', type: 'mysql' }, [MYSQL, SSH]),
    ).toEqual({ category: CREDENTIAL_CATEGORIES[0] });
    expect(
      resolveCredentialLocate({ category: 'database', type: 'ssh' }, [MYSQL, SSH]),
    ).toEqual({ category: 'database' });
    expect(
      resolveCredentialLocate({ category: 'database', type: 'missing' }, [MYSQL, SSH]),
    ).toEqual({ category: 'database' });
  });

  it('accepts extra categories only after their types are known', () => {
    expect(resolveCredentialLocate({ category: 'secret-store' }, [])).toEqual({
      category: CREDENTIAL_CATEGORIES[0],
    });
    expect(resolveCredentialLocate({ category: 'secret-store', type: 'vault' }, [CUSTOM])).toEqual({
      category: 'secret-store',
      type: 'vault',
    });
  });
});
