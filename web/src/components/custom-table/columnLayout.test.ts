import { describe, expect, it } from 'vitest';
import {
  DEFAULT_COL_WIDTH,
  estimateContentMinWidth,
  resolveColumnLayout,
  scaleWidthsToContainer,
} from './columnLayout';

describe('resolveColumnLayout fill width', () => {
  const columns = [
    { key: 'name', width: 200 },
    { key: 'status', width: 120 },
    { key: 'action', width: 80 },
  ];

  it('scales declared column widths to the pane when the table would otherwise leave a gap', () => {
    const layout = resolveColumnLayout({
      autoScrollX: true,
      columns,
      columnWidths: {},
      containerWidth: 800,
    });

    expect(layout.scrollX).toBeUndefined();
    expect(layout.tableLayout).toBe('fixed');
    expect(layout.widths).toEqual(scaleWidthsToContainer([200, 120, 80], 800));
    expect((layout.widths as number[]).reduce((sum, width) => sum + width, 0)).toBe(800);
  });

  it('locks default pixel widths and enables horizontal scroll when columns overflow', () => {
    const layout = resolveColumnLayout({
      autoScrollX: true,
      columns: [
        { key: 'a' },
        { key: 'b' },
        { key: 'c' },
        { key: 'd' },
      ],
      columnWidths: {},
      containerWidth: 400,
    });

    expect(layout.scrollX).toBe(DEFAULT_COL_WIDTH * 4);
    expect(layout.tableLayout).toBe('fixed');
    expect(layout.widths).toEqual([
      DEFAULT_COL_WIDTH,
      DEFAULT_COL_WIDTH,
      DEFAULT_COL_WIDTH,
      DEFAULT_COL_WIDTH,
    ]);
  });

  it('keeps fixed columns and stretches the rest so action columns do not become a white gap', () => {
    const layout = resolveColumnLayout({
      autoScrollX: true,
      columns: [
        { key: 'name', width: 200 },
        { key: 'status', width: 120 },
        { key: 'action', width: 80, fixed: 'right' },
      ],
      columnWidths: {},
      containerWidth: 800,
    });

    expect(layout.widths).toEqual([450, 270, 80]);
    expect((layout.widths as number[]).reduce((sum, width) => sum + width, 0)).toBe(800);
  });

  it('scales unspecified columns from the default min width so the table still fills', () => {
    const layout = resolveColumnLayout({
      autoScrollX: true,
      columns: [
        { key: 'name', width: 160 },
        { key: 'desc' },
      ],
      columnWidths: {},
      containerWidth: 1000,
    });

    expect(layout.scrollX).toBeUndefined();
    expect(layout.widths).toEqual(
      scaleWidthsToContainer([160, DEFAULT_COL_WIDTH], 1000),
    );
  });
});

describe('estimateContentMinWidth', () => {
  it('counts unspecified columns as the default min width', () => {
    expect(estimateContentMinWidth([
      { key: 'a', width: 100 },
      { key: 'b' },
    ])).toBe(100 + DEFAULT_COL_WIDTH);
  });
});
