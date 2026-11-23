import { describe, expect, it } from 'vitest';
import { resolveAccessCmdbFollowUp } from '../automaticPolicyApply';

const licensed = [{ name: 'cmdb' }, { name: 'monitor' }] as never;

describe('resolveAccessCmdbFollowUp', () => {
  it('offers a cmdb sync from newly accessed instance ids', () => {
    expect(resolveAccessCmdbFollowUp({
      clientData: licensed,
      clientLoading: false,
      objectName: 'Host',
      collectResult: { instance_ids: [' m-1 ', 'm-2'] },
    })).toEqual({ ids: ['m-1', 'm-2'], overflow: 0 });
  });

  it('falls back to collect params when the result has no instance ids', () => {
    expect(resolveAccessCmdbFollowUp({
      clientData: licensed,
      clientLoading: false,
      objectName: 'Host',
      collectResult: {},
      collectParams: { instances: [{ instance_id: 'm-3' }] },
    })).toEqual({ ids: ['m-3'], overflow: 0 });
  });

  it('does not offer when the object is unmapped or unlicensed', () => {
    expect(resolveAccessCmdbFollowUp({
      clientData: licensed,
      clientLoading: false,
      objectName: 'Weblogic',
      collectResult: { instance_ids: ['m-1'] },
    })).toBeNull();
    expect(resolveAccessCmdbFollowUp({
      clientData: [{ name: 'monitor' }] as never,
      clientLoading: false,
      objectName: 'Host',
      collectResult: { instance_ids: ['m-1'] },
    })).toBeNull();
    expect(resolveAccessCmdbFollowUp({
      clientData: licensed,
      clientLoading: false,
      objectName: 'Host',
      collectResult: { instance_ids: [] },
    })).toBeNull();
  });
});
