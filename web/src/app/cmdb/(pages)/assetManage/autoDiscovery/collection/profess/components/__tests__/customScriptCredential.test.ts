import { describe, expect, it } from 'vitest';
import { customScriptHostOsQuery } from '../hostOsQuery';

describe('customScriptHostOsQuery', () => {
  it('filters linux plugins to linux hosts and windows plugins to windows hosts', () => {
    expect(customScriptHostOsQuery('linux')).toEqual({ field: 'os_type', type: 'list_any[]', value: ['1'] });
    expect(customScriptHostOsQuery('windows')).toEqual({ field: 'os_type', type: 'list_any[]', value: ['2'] });
  });
});
