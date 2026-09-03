import { describe, expect, it } from 'vitest';
import {
  extractHighlightTerms,
  splitHighlightedText
} from '../searchHighlight';

describe('extractHighlightTerms', () => {
  it('returns nothing for empty or wildcard queries', () => {
    expect(extractHighlightTerms('')).toEqual([]);
    expect(extractHighlightTerms(' * ')).toEqual([]);
  });

  it('keeps quoted phrases and unquoted tokens, skipping operators and field names', () => {
    expect(extractHighlightTerms('error AND host.name:"api server" OR timeout')).toEqual([
      'api server',
      'timeout',
      'error'
    ]);
    expect(extractHighlightTerms('host.name:web01')).toEqual(['web01']);
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
});
