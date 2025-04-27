import { Graph } from '@antv/x6';
import { useEffect, useCallback } from 'react';
import { getIconUrl } from '@/app/cmdb/utils/common';
import { useGraphStore, useGraphInstance } from '@antv/xflow';
import { TopoDataProps, NodeData } from '@/app/cmdb/types/assetData';

const CONFIG = {
  verticalGap: 100,
  horizontalGap: 400,
  defaultWidth: 200,
  defaultHeight: 80,
  maxExpandedLevel: 3,
  childNodeVerticalGap: 80,
  minVerticalGap: 100,
  maxVerticalGap: 150,
  nodeRatioThreshold: 0.5,
};

export const InitNode: React.FC<TopoDataProps> = ({
  topoData,
  modelList,
  assoTypeList,
}) => {
  const initData = useGraphStore((state) => state.initData);
  const graph = useGraphInstance();
  const setInitData = useCallback(() => {
    if (topoData.src_result || topoData.dst_result) {
      const srcResult: any = topoData.src_result;
      const dstResult: any = topoData.dst_result;
      const hasSrc = srcResult?.children?.length > 0;
      const hasDst = dstResult?.children?.length > 0;
      const srcData = transformData(srcResult, true, { hasSrc, hasDst });
      const dstData = transformData(dstResult, false, { hasSrc, hasDst });
      const srcFirstNode = srcData?.nodes?.[0];
      const dstFirstNode = dstData?.nodes?.[0];
      if (srcFirstNode && dstFirstNode) {
        srcFirstNode.data.children = [
          ...srcFirstNode.data.children,
          ...dstFirstNode.data.children,
        ];
      }
      initData({
        nodes: [...srcData.nodes, ...dstData.nodes],
        edges: [...srcData.edges, ...dstData.edges],
      });
    } else {
      initData({
        nodes: [],
        edges: [],
      });
    }
  }, [initData, topoData]);

  useEffect(() => {
    registerCollapseNode();
    setInitData();
    setTimeout(() => {
      graph?.getNodes().forEach((node) => {
        if (node.getData().defaultShow) {
          node.show();
        } else {
          node.hide();
        }
      });
    }, 0);
    graph?.on('node:collapse', handleCollapse);
    graph?.on('node:click', linkToDetail);
    return () => {
      graph?.off('node:collapse', handleCollapse);
      graph?.off('node:click', linkToDetail);
    };
  }, [setInitData]);

  const handleCollapse = (item: any) => {
    const { e, node } = item;
    const target = e.target;
    const isExpanded = node.getData().expanded;
    const isSrcBtn = target.getAttribute('name') === 'expandBtnL';

    node.setData({ expanded: !isExpanded });

    const btnSelector = isSrcBtn ? 'expandBtnL' : 'expandBtnR';
    node.setAttrs({
      [btnSelector]: {
        d: isExpanded
          ? 'M 3 6 L 9 6 M 6 3 L 6 9 M 1 1 L 11 1 L 11 11 L 1 11 Z'
          : 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z',
      },
    });

    const processChildren = (children: NodeData[], level: number) => {
      children.forEach((child: NodeData) => {
        const childNode = graph?.getCellById(child._id.toString());
        if (childNode) {
          const childData = childNode.getData();
          const isSrcNode = childData.isSrc;
          if ((isSrcBtn && isSrcNode) || (!isSrcBtn && !isSrcNode)) {
            if (isExpanded) {
              childNode.setData({ expanded: false });
              childNode.hide();
              if (childData.children?.length) {
                processChildren(childData.children, level + 1);
              }
            } else {
              if (level === 1) {
                childNode.show();
              }
            }
          }
        }
      });
    };

    const children = node.getData().children || [];
    processChildren(children, 1);
  };

  const linkToDetail = (data: any) => {
    const { e, node } = data;
    const target = e.target;
    if (
      target.tagName === 'path' &&
      target.getAttribute('event') === 'node:collapse'
    ) {
      return;
    }
    const row = node?.getData();
    const params: any = {
      icn: '',
      model_name: showModelName(row.modelId),
      model_id: row.modelId,
      classification_id: '',
      inst_id: node.id,
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/cmdb/assetData/detail/baseInfo?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const showModelName = (id: string) => {
    return modelList.find((item) => item.model_id === id)?.model_name || '--';
  };

  const getExpandBtnPath = (hasChild: boolean, isExpanded: boolean) => {
    if (!hasChild) return 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z';
    return isExpanded
      ? 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z'
      : 'M 3 6 L 9 6 M 6 3 L 6 9 M 1 1 L 11 1 L 11 11 L 1 11 Z';
  };

  const collectLevelInfo = (
    node: NodeData,
    parentId: string | null,
    level: number,
    levelNodes: {
      [key: number]: Array<{
        id: string;
        parentId: string | null;
        node: NodeData;
      }>;
    }
  ) => {
    if (!node._id) return;

    const id = node._id.toString();
    if (!levelNodes[level]) levelNodes[level] = [];

    levelNodes[level].push({ id, parentId, node });

    if (node.children) {
      node.children.forEach((child) =>
        collectLevelInfo(child, id, level + 1, levelNodes)
      );
    }
  };

  const calculateNodePosition = (
    levelNodes: {
      [key: number]: Array<{
        id: string;
        parentId: string | null;
        node: NodeData;
      }>;
    },
    nodePositions: { [key: string]: { x: number; y: number } },
    isSrc: boolean
  ) => {
    if (!levelNodes[1]?.[0]) return;

    const rootId = levelNodes[1][0].id;
    nodePositions[rootId] = { x: 0, y: 0 };

    const maxLevel = Math.max(...Object.keys(levelNodes).map(Number));
    for (let level = 2; level <= maxLevel; level++) {
      if (!levelNodes[level]) continue;

      const currentLevelNodes = levelNodes[level];
      const parentLevelNodes = levelNodes[level - 1] || [];
      const nodeRatio = currentLevelNodes.length / (parentLevelNodes.length || 1);

      const nodeCount = currentLevelNodes.length;
      const verticalGap = Math.max(
        CONFIG.minVerticalGap,
        Math.min(CONFIG.maxVerticalGap, CONFIG.verticalGap / Math.sqrt(nodeCount))
      );

      if (nodeRatio < CONFIG.nodeRatioThreshold && level > 2) {
        const nodesByParent: { [parentId: string]: typeof currentLevelNodes } = {};
        currentLevelNodes.forEach(node => {
          if (!node.parentId) return;
          if (!nodesByParent[node.parentId]) {
            nodesByParent[node.parentId] = [];
          }
          nodesByParent[node.parentId].push(node);
        });

        Object.entries(nodesByParent).forEach(([parentId, children]) => {
          const parentPos = nodePositions[parentId];
          if (!parentPos) return;

          const totalHeight = (children.length - 1) * verticalGap;
          const startY = parentPos.y - totalHeight / 2;

          children.forEach((child, index) => {
            nodePositions[child.id] = {
              x: isSrc 
                ? parentPos.x - CONFIG.horizontalGap
                : parentPos.x + CONFIG.horizontalGap,
              y: startY + index * verticalGap
            };
          });
        });
      } else {
        const totalHeight = (nodeCount - 1) * verticalGap;
        const startY = -totalHeight / 2;

        currentLevelNodes.forEach((nodeInfo, index) => {
          nodePositions[nodeInfo.id] = {
            x: isSrc ? -CONFIG.horizontalGap * (level - 1) : CONFIG.horizontalGap * (level - 1),
            y: startY + index * verticalGap,
          };
        });
      }
    }
  };

  const createNodesAndEdges = (
    node: NodeData,
    parentId: string | null,
    levelNodes: {
      [key: number]: Array<{
        id: string;
        parentId: string | null;
        node: NodeData;
      }>;
    },
    nodePositions: { [key: string]: { x: number; y: number } },
    isSrc: boolean,
    nodes: any[],
    edges: any[],
    layoutInfo: { hasSrc: boolean; hasDst: boolean }
  ) => {
    if (!node._id) return;

    const id = node._id.toString();
    const hasChild = !!node.children?.length;
    const position = nodePositions[id];
    const { hasSrc, hasDst } = layoutInfo;

    if (!position) return;

    const level = Object.keys(levelNodes).find((lvl) =>
      levelNodes[Number(lvl)]?.some((n) => n.id === id)
    );
    const currentLevel = Number(level);
    const isExpanded = currentLevel < CONFIG.maxExpandedLevel;
    const hasLeftBtn =(currentLevel === 1 && hasSrc) || (currentLevel !== 1 && isSrc && hasChild)
    const hasRightBtn = (currentLevel === 1 && hasDst) || (currentLevel !== 1 && !isSrc && hasChild);

    nodes.push({
      id,
      x: position.x,
      y: position.y,
      width: CONFIG.defaultWidth,
      height: CONFIG.defaultHeight,
      shape: 'custom-rect',
      attrs: {
        image: {
          'xlink:href': getIconUrl({ icn: '', model_id: node.model_id }),
        },
        tooltip1: {
          text: node.inst_name,
        },
        label1: { text: node.inst_name, title: node.inst_name },
        tooltip2: {
          text: showModelName(node.model_id),
        },
        label2: {
          text: showModelName(node.model_id),
          title: showModelName(node.model_id),
        },
        expandBtnL: {
          stroke: hasLeftBtn ? 'var(--color-border-3)' : '',
          fill: hasLeftBtn ? 'var(--color-bg-1)' : 'transparent',
          d: getExpandBtnPath(hasLeftBtn, isExpanded),
        },
        expandBtnR: {
          stroke: hasRightBtn ? 'var(--color-border-3)' : '',
          fill:  hasRightBtn ? 'var(--color-bg-1)' : 'transparent',
          d: getExpandBtnPath(hasRightBtn, isExpanded),
        },
      },
      data: {
        defaultShow: currentLevel <= CONFIG.maxExpandedLevel,
        expanded: isExpanded,
        children: hasChild ? node.children : [],
        modelId: node.model_id,
        isSrc: isSrc,
        level: currentLevel,
      },
    });

    if (parentId) {
      edges.push({
        source: parentId,
        target: id,
        attrs: {
          line: { stroke: 'var(--color-border-3)', strokeWidth: 1 },
        },
        label: {
          attrs: {
            text: {
              text:
                assoTypeList.find((tex) => tex.asst_id === node.asst_id)
                  ?.asst_name || '--',
              fill: 'var(--color-text-4)',
            },
            rect: { fill: 'var(--color-bg-1)', stroke: 'none' },
          },
        },
        router: { name: 'er', args: { direction: 'H', offset: 20 } },
      });
    }

    if (node.children) {
      node.children.forEach((child) =>
        createNodesAndEdges(
          child,
          id,
          levelNodes,
          nodePositions,
          isSrc,
          nodes,
          edges,
          layoutInfo
        )
      );
    }
  };

  const transformData = (data: NodeData, isSrc: boolean, layoutInfo: { hasSrc: boolean; hasDst: boolean }) => {
    const nodes: any[] = [];
    const edges: any[] = [];

    const nodePositions: { [key: string]: { x: number; y: number } } = {};

    const levelNodes: {
      [key: number]: Array<{
        id: string;
        parentId: string | null;
        node: NodeData;
      }>;
    } = {};

    collectLevelInfo(data, null, 1, levelNodes);
    calculateNodePosition(levelNodes, nodePositions, isSrc);
    createNodesAndEdges(
      data,
      null,
      levelNodes,
      nodePositions,
      isSrc,
      nodes,
      edges,
      layoutInfo
    );
    return { nodes, edges };
  };

  const registerCollapseNode = () => {
    Graph.registerNode(
      'custom-rect',
      {
        inherit: 'rect',
        markup: [
          {
            tagName: 'rect',
            selector: 'body',
          },
          {
            tagName: 'line',
            selector: 'divider',
          },
          {
            tagName: 'image',
            selector: 'image',
          },
          {
            tagName: 'title',
            selector: 'tooltip1',
          },
          {
            tagName: 'text',
            selector: 'label1',
          },
          {
            tagName: 'title',
            selector: 'tooltip2',
          },
          {
            tagName: 'text',
            selector: 'label2',
          },
          {
            tagName: 'path',
            selector: 'expandBtnL',
          },
          {
            tagName: 'path',
            selector: 'expandBtnR',
          },
        ],
        attrs: {
          body: {
            stroke: 'var(--color-border-3)',
            strokeWidth: 1,
            fill: 'var(--color-bg-1)',
            rx: 6,
            ry: 6,
            width: 200,
            height: 80,
          },
          image: {
            width: 40,
            height: 40,
            x: 10,
            y: 18,
          },
          divider: {
            x1: 60,
            y1: 0,
            x2: 60,
            y2: 80,
            stroke: 'var(--color-border-3)',
            strokeWidth: 1,
          },
          tooltip1: {
            text: '',
          },
          label1: {
            refX: 0.4,
            refY: 0.4,
            textWrap: {
              width: 120,
              height: 20,
              ellipsis: true,
            },
            textAnchor: 'center',
            textVerticalAnchor: 'middle',
            fontSize: 14,
            fill: 'var(--color-text-1)',
          },
          tooltip2: {
            text: '',
          },
          label2: {
            refX: 0.4,
            refY: 0.7,
            textWrap: {
              width: 120,
              height: 20,
              ellipsis: true,
            },
            textAnchor: 'center',
            textVerticalAnchor: 'middle',
            fontSize: 14,
            fill: 'var(--color-text-4)',
          },
          expandBtnL: {
            name: 'expandBtnL',
            d: 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z',
            fill: 'red',
            cursor: 'pointer',
            refX: 1,
            refDx: -207,
            refY: 0.42,
            stroke: 'var(--color-text-4)',
            strokeWidth: 1,
            event: 'node:collapse',
            zIndex: 99,
          },
          expandBtnR: {
            name: 'expandBtnR',
            d: 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z',
            fill: 'red',
            cursor: 'pointer',
            refX: 1,
            refDx: -7,
            refY: 0.42,
            stroke: 'var(--color-text-4)',
            strokeWidth: 1,
            event: 'node:collapse',
            zIndex: 99,
          },
        },
        data: {
          expanded: false,
        },
        draggable: true,
        zIndex: 10,
      },
      true
    );
  };

  return null;
};
