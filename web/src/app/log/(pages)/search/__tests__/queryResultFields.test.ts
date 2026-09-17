import { describe, expect, it } from 'vitest';

import { mergeSearchResultFields } from '../queryResultFields';

describe('mergeSearchResultFields', () => {
  it('keeps catalog fields when there are no result rows', () => {
    expect(mergeSearchResultFields(['host', 'message'], [])).toEqual([
      'host',
      'message'
    ]);
  });

  it('adds extract fields from current search rows into the optional field list', () => {
    expect(
      mergeSearchResultFields(
        ['message', 'source_ip', 'source_port', 'timestamp'],
        [
          {
            id: 'row-1',
            _time: '2026-09-14T09:36:51Z',
            message: 'flow unknown:0 -> unknown:0',
            source: 'unknown',
            source_port: '0',
            target: 'unknown',
            target_port: '0'
          }
        ]
      )
    ).toEqual([
      'message',
      'source',
      'source_ip',
      'source_port',
      'target',
      'target_port',
      'timestamp'
    ]);
  });

  it('does not expose the client row id as a selectable field', () => {
    expect(
      mergeSearchResultFields(['message'], [{ id: 'client-id', message: 'ok' }])
    ).toEqual(['message']);
  });
});
