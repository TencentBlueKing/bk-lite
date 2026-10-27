import { describe, expect, it } from 'vitest';
import { insertTextAtRange } from '../insert-text';

describe('insertTextAtRange', () => {
  it('appends when the editor has no cursor', () => {
    const result = insertTextAtRange('echo hi\n', null, '$BK_JOB_USER');
    expect(result).toEqual({
      value: 'echo hi\n$BK_JOB_USER',
      cursor: { row: 1, column: 12 },
    });
  });

  it('inserts at the cursor on a later line', () => {
    const result = insertTextAtRange('echo \nprint()', { start: { row: 1, column: 6 }, end: { row: 1, column: 6 } }, 'BK_JOB_ID');
    expect(result.value).toBe('echo \nprint(BK_JOB_ID)');
    expect(result.cursor).toEqual({ row: 1, column: 15 });
  });

  it('replaces the current selection', () => {
    const result = insertTextAtRange('echo NAME', { start: { row: 0, column: 5 }, end: { row: 0, column: 9 } }, '$BK_JOB_USER');
    expect(result.value).toBe('echo $BK_JOB_USER');
    expect(result.cursor).toEqual({ row: 0, column: 17 });
  });

  it('keeps the script unchanged when the token is empty', () => {
    const result = insertTextAtRange('echo hi', { start: { row: 0, column: 4 }, end: { row: 0, column: 4 } }, '');
    expect(result.value).toBe('echo hi');
    expect(result.cursor).toEqual({ row: 0, column: 4 });
  });
});
