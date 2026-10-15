import { describe, expect, it } from 'vitest';
import { opsTableCellTextStyle, resolveOpsTableColumnWidth } from '../opsTableColumn';

describe('resolveOpsTableColumnWidth', () => {
  it('keeps a positive configured width', () => {
    expect(resolveOpsTableColumnWidth(200)).toBe(200);
  });

  it('drops missing or non-positive widths', () => {
    expect(resolveOpsTableColumnWidth(undefined)).toBeUndefined();
    expect(resolveOpsTableColumnWidth(0)).toBeUndefined();
    expect(resolveOpsTableColumnWidth(-12)).toBeUndefined();
    expect(resolveOpsTableColumnWidth(Number.NaN)).toBeUndefined();
  });
});

describe('opsTableCellTextStyle', () => {
  it('clips text to the cell instead of a fixed pixel cap', () => {
    expect(opsTableCellTextStyle()).toMatchObject({
      width: '100%',
      maxWidth: '100%',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
    });
    expect(opsTableCellTextStyle()).not.toHaveProperty('maxWidth', 260);
  });

  it('keeps a mapped color on the same full-cell box', () => {
    expect(opsTableCellTextStyle('#ff5b6e')).toMatchObject({
      width: '100%',
      color: '#ff5b6e',
      fontWeight: 600,
    });
  });
});
