import { describe, expect, it } from 'vitest';

import {
  isUrlColonyObject,
  isUrlSortObject,
  readUrlColonyIds,
  readUrlTableSort,
  resolveColonyAfterEnumLoad,
} from '../viewListUrlPrefill';

const params = (query: string) => new URLSearchParams(query);

describe('isUrlColonyObject / isUrlSortObject', () => {
  it('treats Process, Pod and Node as colony consumers', () => {
    expect(isUrlColonyObject('Process')).toBe(true);
    expect(isUrlColonyObject('Pod')).toBe(true);
    expect(isUrlColonyObject('Node')).toBe(true);
    expect(isUrlColonyObject('Host')).toBe(false);
    expect(isUrlColonyObject('K3SPod')).toBe(false);
  });

  it('sorts only Pod and Node lists from the URL', () => {
    expect(isUrlSortObject('Pod')).toBe(true);
    expect(isUrlSortObject('Node')).toBe(true);
    expect(isUrlSortObject('Process')).toBe(false);
    expect(isUrlSortObject('Host')).toBe(false);
  });
});

describe('readUrlColonyIds', () => {
  it('prefills vm_params.instance_id for Process/Pod/Node', () => {
    const search = params('vm_params.instance_id=cluster-a');
    expect(readUrlColonyIds(search, 'Pod')).toEqual(['cluster-a']);
    expect(readUrlColonyIds(search, 'Node')).toEqual(['cluster-a']);
    expect(readUrlColonyIds(search, 'Process')).toEqual(['cluster-a']);
    expect(readUrlColonyIds(search, 'Host')).toEqual([]);
    expect(readUrlColonyIds(params(''), 'Pod')).toEqual([]);
  });
});

describe('readUrlTableSort', () => {
  it('maps display_field_key ordering onto column_key', () => {
    const search = params(
      'ordering=K8S%3A%3Apod_cpu_utilization&order=desc'
    );
    expect(
      readUrlTableSort(search, [
        {
          column_key: 'cpu',
          metrics: [{ plugin: 'K8S', metric: 'pod_cpu_utilization' }],
        },
      ])
    ).toEqual({ key: 'cpu', order: 'descend' });
  });

  it('keeps the raw ordering key when no column matches', () => {
    expect(
      readUrlTableSort(params('ordering=K8S::pod_memory_utilization&order=asc'), [])
    ).toEqual({ key: 'K8S::pod_memory_utilization', order: 'ascend' });
  });

  it('returns null without ordering so restart Top stays unsorted', () => {
    expect(readUrlTableSort(params('vm_params.instance_id=cluster-a'), [])).toBeNull();
  });
});

describe('resolveColonyAfterEnumLoad', () => {
  it('keeps dashboard cluster ids even when the VM enum is missing them', () => {
    expect(resolveColonyAfterEnumLoad('Pod', ['cluster-a'])).toEqual(['cluster-a']);
    expect(resolveColonyAfterEnumLoad('Node', ['cluster-a'])).toEqual(['cluster-a']);
  });

  it('keeps ids when the enum is empty so Process deep-links still work', () => {
    expect(resolveColonyAfterEnumLoad('Process', ['host-1'])).toEqual(['host-1']);
  });

  it('wipes leftover colony for objects that do not consume instance_id', () => {
    expect(resolveColonyAfterEnumLoad('Host', ['cluster-a'])).toEqual([]);
    expect(resolveColonyAfterEnumLoad('K3SPod', ['cluster-a'])).toEqual([]);
  });
});
