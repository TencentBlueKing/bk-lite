import { describe, expect, it } from 'vitest';
import {
  applyInstancePageSlices,
  collectSettledModelCounts,
  mergePageSelection,
  planCrossModelInstancePage,
  uniqueInstancePageRequests,
} from '../networkStatusTopologyDevicePage';

describe('planCrossModelInstancePage', () => {
  it('pages a single model with the table page number', () => {
    expect(
      planCrossModelInstancePage([{ modelId: 'switch', count: 50 }], 2, 20),
    ).toEqual([
      {
        modelId: 'switch',
        requestPage: 2,
        pageSize: 20,
        sliceStart: 0,
        take: 20,
      },
    ]);
  });

  it('walks models in order so one table page can span two models', () => {
    expect(
      planCrossModelInstancePage(
        [
          { modelId: 'switch', count: 15 },
          { modelId: 'router', count: 15 },
        ],
        1,
        20,
      ),
    ).toEqual([
      {
        modelId: 'switch',
        requestPage: 1,
        pageSize: 20,
        sliceStart: 0,
        take: 15,
      },
      {
        modelId: 'router',
        requestPage: 1,
        pageSize: 20,
        sliceStart: 0,
        take: 5,
      },
    ]);
  });

  it('continues from the leftover of the previous model on the next table page', () => {
    expect(
      planCrossModelInstancePage(
        [
          { modelId: 'switch', count: 15 },
          { modelId: 'router', count: 15 },
        ],
        2,
        20,
      ),
    ).toEqual([
      {
        modelId: 'router',
        requestPage: 1,
        pageSize: 20,
        sliceStart: 5,
        take: 10,
      },
    ]);
  });

  it('splits a slice that crosses two CMDB pages', () => {
    expect(
      planCrossModelInstancePage(
        [
          { modelId: 'router', count: 15 },
          { modelId: 'switch', count: 50 },
        ],
        2,
        20,
      ),
    ).toEqual([
      {
        modelId: 'switch',
        requestPage: 1,
        pageSize: 20,
        sliceStart: 5,
        take: 15,
      },
      {
        modelId: 'switch',
        requestPage: 2,
        pageSize: 20,
        sliceStart: 0,
        take: 5,
      },
    ]);
  });
});

describe('applyInstancePageSlices', () => {
  it('stitches fetched model pages back into one table page', () => {
    const slices = planCrossModelInstancePage(
      [
        { modelId: 'switch', count: 15 },
        { modelId: 'router', count: 15 },
      ],
      1,
      20,
    );
    const pages = new Map<string, unknown[]>([
      ['switch:1', Array.from({ length: 15 }, (_, index) => `s${index}`)],
      ['router:1', Array.from({ length: 15 }, (_, index) => `r${index}`)],
    ]);

    expect(applyInstancePageSlices(slices, pages)).toEqual([
      ...Array.from({ length: 15 }, (_, index) => `s${index}`),
      ...Array.from({ length: 5 }, (_, index) => `r${index}`),
    ]);
  });
});

describe('uniqueInstancePageRequests', () => {
  it('requests each model page once', () => {
    expect(
      uniqueInstancePageRequests([
        {
          modelId: 'switch',
          requestPage: 2,
          pageSize: 20,
          sliceStart: 0,
          take: 15,
        },
        {
          modelId: 'switch',
          requestPage: 2,
          pageSize: 20,
          sliceStart: 0,
          take: 5,
        },
      ]),
    ).toEqual([{ modelId: 'switch', requestPage: 2, pageSize: 20 }]);
  });
});

describe('collectSettledModelCounts', () => {
  it('keeps counts from models that loaded and treats failures as empty', () => {
    expect(
      collectSettledModelCounts(['switch', 'router'], [
        { status: 'fulfilled', value: { count: 40 } },
        { status: 'rejected', reason: new Error('denied') },
      ]),
    ).toEqual([
      { modelId: 'switch', count: 40 },
      { modelId: 'router', count: 0 },
    ]);
  });
});

describe('mergePageSelection', () => {
  it('keeps selections from other pages when this page changes', () => {
    expect(
      mergePageSelection(['other', 'page-a'], ['page-a', 'page-b'], ['page-b'], 10),
    ).toEqual({
      next: ['other', 'page-b'],
      truncated: false,
    });
  });

  it('selects the current page without dropping other pages', () => {
    expect(
      mergePageSelection(['other'], ['page-a', 'page-b'], ['page-a', 'page-b'], 10),
    ).toEqual({
      next: ['other', 'page-a', 'page-b'],
      truncated: false,
    });
  });

  it('stops at the node limit and reports truncation', () => {
    expect(
      mergePageSelection(['keep'], ['a', 'b', 'c'], ['a', 'b', 'c'], 2),
    ).toEqual({
      next: ['keep', 'a'],
      truncated: true,
    });
  });

  it('clears only the current page', () => {
    expect(
      mergePageSelection(['keep', 'page-a'], ['page-a', 'page-b'], [], 10),
    ).toEqual({
      next: ['keep'],
      truncated: false,
    });
  });
});
