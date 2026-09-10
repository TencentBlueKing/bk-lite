import { describe, expect, it } from 'vitest';
import {
  extractHighlightTerms,
  isLogContentField,
  splitHighlightedText
} from '../searchHighlight';

describe('extractHighlightTerms', () => {
  it('returns nothing for empty or wildcard queries', () => {
    expect(extractHighlightTerms('')).toEqual([]);
    expect(extractHighlightTerms(' * ')).toEqual([]);
  });

  it('keeps log-content tokens and skips operators and non-content field filters', () => {
    expect(extractHighlightTerms('error AND host.name:"api server" OR timeout')).toEqual([
      'timeout',
      'error'
    ]);
    expect(extractHighlightTerms('host.name:web01')).toEqual([]);
    expect(extractHighlightTerms('_msg:"api server" AND timeout')).toEqual([
      'api server',
      'timeout'
    ]);
    expect(extractHighlightTerms('message:web01')).toEqual(['web01']);
  });

  it('does not treat field-value syntax as highlight terms', () => {
    expect(extractHighlightTerms('udp AND "@metadata.beat":"packetbeat"')).toEqual(['udp']);
    expect(extractHighlightTerms('"@timestamp":"2026-09-08T07:39:45.563Z"')).toEqual([]);
  });

  it('keeps colons that belong to a quoted content phrase', () => {
    expect(extractHighlightTerms('"error: cannot find file"')).toEqual([
      'error: cannot find file'
    ]);
  });
});

describe('isLogContentField', () => {
  it('only treats message body fields as log content', () => {
    expect(isLogContentField('message')).toBe(true);
    expect(isLogContentField('_msg')).toBe(true);
    expect(isLogContentField('@metadata.beat')).toBe(false);
    expect(isLogContentField('agent.name')).toBe(false);
  });
});

describe('splitHighlightedText', () => {
  it('highlights matches case-insensitively and merges overlaps', () => {
    expect(splitHighlightedText('Connection Timeout in timeout handler', ['timeout'])).toEqual([
      { text: 'Connection ', match: false },
      { text: 'Timeout', match: true },
      { text: ' in ', match: false },
      { text: 'timeout', match: true },
      { text: ' handler', match: false }
    ]);
    expect(splitHighlightedText('aaa', ['a', 'aa'])).toEqual([
      { text: 'aaa', match: true }
    ]);
  });

  it('returns the original text when nothing matches', () => {
    expect(splitHighlightedText('access granted', ['error'])).toEqual([
      { text: 'access granted', match: false }
    ]);
  });

  it('does not highlight field-filter values or colons in log content', () => {
    const terms = extractHighlightTerms('udp AND "@metadata.beat":"packetbeat"');
    expect(splitHighlightedText('udp 127.0.0.1:53 -> 127.0.0.1:43165', terms)).toEqual([
      { text: 'udp', match: true },
      { text: ' 127.0.0.1:53 -> 127.0.0.1:43165', match: false }
    ]);
    expect(splitHighlightedText('packetbeat', terms)).toEqual([
      { text: 'packetbeat', match: false }
    ]);
    expect(splitHighlightedText('2026-09-08T07:39:45.563Z', terms)).toEqual([
      { text: '2026-09-08T07:39:45.563Z', match: false }
    ]);
  });
});
