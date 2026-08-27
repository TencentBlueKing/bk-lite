import { describe, expect, it } from 'vitest';
import { findInstallIpUniquenessError } from '../ipUniqueness';

describe('controller install IP uniqueness', () => {
  it('rejects two rows with the same IP', () => {
    expect(
      findInstallIpUniquenessError([
        { ip: '10.0.0.1' },
        { ip: '10.0.0.1' }
      ])
    ).toEqual({ kind: 'duplicate', ip: '10.0.0.1' });
  });

  it('allows the same IP when it is not compared across cloud regions', () => {
    expect(
      findInstallIpUniquenessError([{ ip: '10.0.0.1' }], [])
    ).toBeNull();
  });

  it('rejects an IP that already exists in the current cloud region', () => {
    expect(
      findInstallIpUniquenessError([{ ip: '10.0.0.8' }], ['10.0.0.8'])
    ).toEqual({ kind: 'exists', ip: '10.0.0.8' });
  });

  it('treats an IP already in the current install table as a duplicate', () => {
    expect(
      findInstallIpUniquenessError([{ ip: '10.0.0.3' }], [], ['10.0.0.3'])
    ).toEqual({ kind: 'duplicate', ip: '10.0.0.3' });
  });

  it('ignores empty IP cells', () => {
    expect(
      findInstallIpUniquenessError([{ ip: '' }, { ip: null }, { ip: '10.0.0.2' }])
    ).toBeNull();
  });
});
