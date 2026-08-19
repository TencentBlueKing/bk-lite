import { describe, expect, it } from 'vitest';
import {
  buildOptionSheetDefinitions,
  buildOrganizationOptions,
  findExcelImportColumn,
  resolveOrganizationCell
} from '../excelImportUtils';

describe('controller install Excel organization options', () => {
  it('uses readable full paths from the organization tree', () => {
    expect(
      buildOrganizationOptions([
        {
          id: '1',
          name: 'Headquarters',
          subGroups: [
            { id: '2', name: 'Platform' },
            { id: '3', name: 'Operations' }
          ]
        }
      ])
    ).toEqual([
      { label: 'Headquarters', name: 'Headquarters', value: 1 },
      { label: 'Headquarters/Platform', name: 'Platform', value: 2 },
      { label: 'Headquarters/Operations', name: 'Operations', value: 3 }
    ]);
  });

  it('keeps the organization sheet visible and other option sheets hidden', () => {
    expect(
      buildOptionSheetDefinitions(
        [
          { label: 'Org/Team', type: 'group_select' },
          {
            label: 'Org/Team',
            type: 'select',
            widget_props: { options: [{ label: 'Password', value: 'pwd' }] }
          }
        ],
        [{ label: 'Headquarters/Platform', name: 'Platform', value: 2 }],
        'Options',
        ['Data']
      )
    ).toEqual([
      {
        columnIndex: 0,
        options: ['Headquarters/Platform'],
        sheetName: 'Org_Team_Options',
        state: 'visible'
      },
      {
        columnIndex: 1,
        options: ['Password'],
        sheetName: 'Org_Team_Options_2',
        state: 'hidden'
      }
    ]);
  });

  it('resolves an exact full organization path to its ID', () => {
    expect(
      resolveOrganizationCell('Headquarters/Platform', [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 },
        { label: 'Branch/Platform', name: 'Platform', value: 3 }
      ])
    ).toEqual({ ids: [2], issues: [] });
  });

  it('accepts a leaf organization name only when it is globally unique', () => {
    expect(
      resolveOrganizationCell('Operations', [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 },
        { label: 'Headquarters/Operations', name: 'Operations', value: 3 }
      ])
    ).toEqual({ ids: [3], issues: [] });
  });

  it('keeps the existing comma-separated multi-organization format', () => {
    expect(
      resolveOrganizationCell('Headquarters/Platform, Operations', [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 },
        { label: 'Headquarters/Operations', name: 'Operations', value: 3 }
      ])
    ).toEqual({ ids: [2, 3], issues: [] });
  });

  it('reports an ambiguous leaf organization name', () => {
    expect(
      resolveOrganizationCell('Platform', [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 },
        { label: 'Branch/Platform', name: 'Platform', value: 3 }
      ])
    ).toEqual({
      ids: [],
      issues: [{ reason: 'ambiguous', value: 'Platform' }]
    });
  });

  it('reports an unknown organization name', () => {
    expect(
      resolveOrganizationCell('Missing', [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 }
      ])
    ).toEqual({
      ids: [],
      issues: [{ reason: 'unknown', value: 'Missing' }]
    });
  });

  it('keeps existing organization IDs compatible', () => {
    expect(
      resolveOrganizationCell('2, 3', [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 },
        { label: 'Headquarters/Operations', name: 'Operations', value: 3 }
      ])
    ).toEqual({ ids: [2, 3], issues: [] });
  });

  it('keeps an empty organization cell empty', () => {
    expect(
      resolveOrganizationCell(null, [
        { label: 'Headquarters/Platform', name: 'Platform', value: 2 }
      ])
    ).toEqual({ ids: null, issues: [] });
  });

  it('maps an organization header by its label without treating the last column as a password', () => {
    const columns = [
      { label: 'IP', name: 'ip', type: 'input' },
      {
        label: 'Organization',
        name: 'organizations',
        type: 'group_select'
      }
    ];

    expect(
      findExcelImportColumn(
        'Organization (Multiple values supported, separated by commas)',
        columns
      )
    ).toBe(columns[1]);
  });
});
