// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildGroupKey } from '../treeExpansionPreference';
import {
  ASSET_MODEL_TREE_NODE_ATTR,
  findClassificationIdForModel,
  planFirstVisitTreeScroll,
  queryAssetModelTreeNode,
  scrollElementIntoContainer,
  shouldFinishFirstVisitTreeScroll,
} from '../treeSelectedNodeScroll';

const modelGroup = [
  {
    classification_id: 'hardware',
    list: [{ model_id: 'physical_server' }],
  },
  {
    classification_id: 'host_manage',
    list: [{ model_id: 'host' }, { model_id: 'virtual_machine' }],
  },
];

const mockBox = (
  element: HTMLElement,
  box: { top: number; height: number; clientHeight?: number }
) => {
  Object.defineProperty(element, 'clientHeight', {
    configurable: true,
    value: box.clientHeight ?? box.height,
  });
  element.getBoundingClientRect = () =>
    ({
      x: 0,
      y: box.top,
      top: box.top,
      bottom: box.top + box.height,
      left: 0,
      right: 0,
      width: 240,
      height: box.height,
      toJSON: () => ({}),
    }) as DOMRect;
};

describe('资产列表首次访问滚动到当前模型', () => {
  it('树未加载时等待，加载后模型不在树中则放弃且不报错', () => {
    expect(
      planFirstVisitTreeScroll({
        alreadyAttempted: false,
        selectedModelId: 'host',
        treeLoaded: false,
        modelGroup: [],
        expandedKeys: [],
      })
    ).toEqual({ action: 'wait' });

    expect(
      planFirstVisitTreeScroll({
        alreadyAttempted: false,
        selectedModelId: 'missing-model',
        treeLoaded: true,
        modelGroup,
        expandedKeys: [buildGroupKey('host_manage')],
      })
    ).toEqual({ action: 'skip' });
  });

  it('首次访问且分组已展开时滚动到当前模型', () => {
    expect(findClassificationIdForModel(modelGroup, 'host')).toBe('host_manage');
    expect(
      planFirstVisitTreeScroll({
        alreadyAttempted: false,
        selectedModelId: 'host',
        treeLoaded: true,
        modelGroup,
        expandedKeys: [buildGroupKey('host_manage')],
      })
    ).toEqual({ action: 'scroll', modelId: 'host' });
  });

  it('当前分组收起时先展开，同一次会话内后续切换不再滚动', () => {
    expect(
      planFirstVisitTreeScroll({
        alreadyAttempted: false,
        selectedModelId: 'host',
        treeLoaded: true,
        modelGroup,
        expandedKeys: [buildGroupKey('hardware')],
      })
    ).toEqual({ action: 'expand', groupKey: buildGroupKey('host_manage') });

    expect(
      planFirstVisitTreeScroll({
        alreadyAttempted: true,
        selectedModelId: 'physical_server',
        treeLoaded: true,
        modelGroup,
        expandedKeys: [buildGroupKey('hardware')],
      })
    ).toEqual({ action: 'skip' });
  });

  it('树仍在加载时找不到节点应继续等，加载完成后才结束', () => {
    expect(shouldFinishFirstVisitTreeScroll({ didScroll: false, loading: true })).toBe(
      false
    );
    expect(
      shouldFinishFirstVisitTreeScroll({ didScroll: false, loading: false })
    ).toBe(true);
    expect(shouldFinishFirstVisitTreeScroll({ didScroll: true, loading: true })).toBe(
      true
    );
  });

  it('按模型 id 查找节点并滚到容器可视区附近', () => {
    const container = document.createElement('div');
    const row = document.createElement('div');
    row.className = 'ant-tree-treenode';
    const title = document.createElement('div');
    title.setAttribute(ASSET_MODEL_TREE_NODE_ATTR, 'host');
    row.appendChild(title);
    container.appendChild(row);
    document.body.appendChild(container);

    mockBox(container, { top: 0, height: 200, clientHeight: 200 });
    mockBox(row, { top: 800, height: 24 });
    container.scrollTop = 0;

    expect(queryAssetModelTreeNode(container, 'host')).toBe(title);
    expect(queryAssetModelTreeNode(container, 'missing')).toBeNull();
    expect(scrollElementIntoContainer(container, title)).toBe(true);
    expect(container.scrollTop).toBe(712);

    document.body.replaceChildren();
  });

  it('资产列表页接入首次定位且只尝试一次', () => {
    const pageSource = readFileSync(
      resolve(process.cwd(), 'src/app/cmdb/(pages)/assetData/page.tsx'),
      'utf8'
    );
    expect(pageSource).toContain('planFirstVisitTreeScroll');
    expect(pageSource).toContain('scrollElementIntoContainer');
    expect(pageSource).toContain('shouldFinishFirstVisitTreeScroll');
    expect(pageSource).toContain('data-asset-model-id');
    expect(pageSource).toContain('firstVisitTreeScrollAttemptedRef');
  });
});
