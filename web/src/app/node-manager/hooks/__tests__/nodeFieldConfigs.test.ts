import { describe, expect, it } from 'vitest';
import { buildNodeSearchFieldConfigs } from '../node';

const t = (key: string) => key;

describe('buildNodeSearchFieldConfigs', () => {
  it('adds active, collector status, and collector name fields', () => {
    const fields = buildNodeSearchFieldConfigs({
      t,
      installMethodMap: {
        auto: { text: 'Auto' },
        manual: { text: 'Manual' }
      }
    });
    const names = fields.map((item) => item.name);
    expect(names.slice(0, 6)).toEqual([
      'name',
      'ip',
      'operating_system',
      'install_method',
      'upgradeable',
      'cpu_architecture'
    ]);
    expect(names).toEqual(
      expect.arrayContaining(['active', 'collector_status', 'collector_name'])
    );
    const active = fields.find((item) => item.name === 'active');
    expect(active?.lookup_expr).toBe('in');
    expect(active?.options?.map((item) => item.id)).toEqual(['true', 'false']);
    const status = fields.find((item) => item.name === 'collector_status');
    expect(status?.options?.map((item) => item.id)).toEqual([
      '0',
      '1',
      '2',
      '3',
      'not_started',
      '10',
      '12'
    ]);
  });
});
