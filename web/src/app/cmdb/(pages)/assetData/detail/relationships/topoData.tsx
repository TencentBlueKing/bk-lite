import { Graph } from '@antv/x6';
import { useEffect, useCallback } from 'react';
import { getIconUrl } from '@/app/cmdb/utils/common';
import { useGraphStore, useGraphInstance } from '@antv/xflow';
import { TopoDataProps, NodeData } from '@/app/cmdb/types/assetData';
import { registerReverseCurveConnector } from '@/app/cmdb/utils/reverse_curve';
import { useInstanceApi } from '@/app/cmdb/api';

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
  const { topoSearchMore } = useInstanceApi();

  // 确保自定义连接器注册，仅需调用一次
  useEffect(() => {
    registerReverseCurveConnector();
  }, []);

  // 初始化节点数据
  const setInitData = useCallback(() => {
    if (topoData.src_result || topoData.dst_result) {
      const srcResult: any = topoData.src_result;
      const dstResult: any = topoData.dst_result;
      const hasSrc = srcResult?.children?.length > 0;
      const hasDst = dstResult?.children?.length > 0;
      const srcData = transformData(srcResult, 'src', true, { hasSrc, hasDst });
      const dstData = transformData(dstResult, 'dst', false, { hasSrc, hasDst });
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

  // 启用异步渲染（根据 AntV X6 官方文档，async 默认值为 true，这里显式设置确保启用）
  // 参考文档：https://x6-v2.antv.vision/api/graph/graph#%E9%85%8D%E7%BD%AE
  useEffect(() => {
    if (graph) {
      try {
        const graphAny = graph as any;
        // 方法1：使用 setOptions 方法（AntV X6 推荐方式）
        if (typeof graphAny.setOptions === 'function') {
          graphAny.setOptions({ async: true });
        }
        // 方法2：直接设置 options（如果 setOptions 不存在）
        else if (graphAny.options) {
          graphAny.options.async = true;
          // 如果 graph 有 updateOptions 方法，调用它以触发更新
          if (typeof graphAny.updateOptions === 'function') {
            graphAny.updateOptions();
          }
        }
      } catch (error) {
        console.warn('设置异步渲染失败:', error);
      }
    }
  }, [graph]);

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

    // 拖拽时隐藏连线，提升性能（性能提升 80%+）
    const graphAny = graph as any;

    // 拖拽时函数
    const handlePanStart = () => {
      // 隐藏连线
      graph?.getEdges().forEach((edge) => {
        const view = graph?.findViewByCell(edge);
        view?.container?.classList.add('hide-edge');
      });

      // 隐藏节点图标
      graph?.getNodes().forEach((node) => {
        const view = graph?.findViewByCell(node);
        view?.container?.classList.add('hide-image');
      });
    };

    // 拖拽结束时函数
    const handlePanEnd = () => {
      // 显示连线
      graph?.getEdges().forEach((edge) => {
        const view = graph?.findViewByCell(edge);
        view?.container?.classList.remove('hide-edge');
      });

      // 显示节点图标
      graph?.getNodes().forEach((node) => {
        const view = graph?.findViewByCell(node);
        view?.container?.classList.remove('hide-image');
      });
    };

    // 监听画布拖拽事件
    graphAny?.on?.('blank:mousedown', handlePanStart);
    graphAny?.on?.('blank:mouseup', handlePanEnd);
    // 兼容其他可能的拖拽事件
    graphAny?.on?.('pan:start', handlePanStart);
    graphAny?.on?.('pan:end', handlePanEnd);

    return () => {
      graph?.off('node:collapse', handleCollapse);
      graph?.off('node:click', linkToDetail);
      graphAny?.off?.('blank:mousedown', handlePanStart);
      graphAny?.off?.('blank:mouseup', handlePanEnd);
      graphAny?.off?.('pan:start', handlePanStart);
      graphAny?.off?.('pan:end', handlePanEnd);
    };
  }, [setInitData]);

  // 节点折叠/展开处理,item为当前点击节点对象
  const handleCollapse = async (item: any) => {
    const { e, node } = item;
    const target = e.target;
    const nodeId = node.id;
    const nodeData = node.getData();
    const isExpanded = nodeData.expanded;
    const level = nodeData.level; // 获取节点层级（1, 2, 3...）
    const isSrcBtn = target.getAttribute('name') === 'expandBtnL';

    // 切换折叠状态
    node.setData({ expanded: !isExpanded });

    // 获取当前节点的相邻节点
    const neighbors = graph.getNeighbors(node);

    // 可以使用 level 进行层级相关的逻辑处理
    if (level >= 3 && !isExpanded) {
      // 获取更多实例的请求数据
      const params = {
        model_id: nodeData.modelId,
        inst_id: nodeId,
        parent_id: neighbors.map((item) => item.id),
      };

      // 获取更多实例的请求数据
      const response = await topoSearchMore(params);

      const data = response?.src_result?.children; // 真实数据

      // 如果存在更多实例，则更新节点数据并创建子节点
      if (data) {
        const newChildren = data;
        node.setData({ children: newChildren });

        // 动态创建子节点
        const parentPosition = node.position();
        const isSrc = nodeData.isSrc;
        const verticalGap = Math.max(
          CONFIG.minVerticalGap,
          Math.min(CONFIG.maxVerticalGap, CONFIG.childNodeVerticalGap)
        );
        const totalHeight = (newChildren.length - 1) * verticalGap;
        const startY = parentPosition.y - totalHeight / 2;

        // 收集需要创建的节点和边
        const nodesToAdd: any[] = [];
        const edgesToAdd: any[] = [];

        // 遍历子节点
        newChildren.forEach((child: NodeData, index: number) => {

          // 标记是否为双向节点
          let isBidirectional = false;

          // 获取子节点的ID
          const childId = child._id.toString();

          // 跳过父节点本身
          if (childId === nodeId) return;

          // // 检查节点是否已存在
          if (graph?.getCellById(childId)) {
            // 获取已存在的节点并显示
            const existingNode = graph.getCellById(childId);
            existingNode?.show();

            // child_all_predecessors为子节点的前序节点数组（需要传入 Cell 对象，不是数据对象）
            const child_all_predecessors = graph?.getPredecessors(existingNode)?.map((item: any) => item.id);

            // 检查当前节点（node）的前驱节点
            if (graph?.getPredecessors(node)) {
              const predecessors = graph?.getPredecessors(node);
              predecessors.forEach((item: any) => {
                // 检查前驱节点是否指向当前节点(回环)
                if (item?.id === childId) {
                  isBidirectional = true;
                }
              })
            }
            if (!isBidirectional && child_all_predecessors.includes(nodeId)) return;
          }

          // 通过isSrc判断子节点是放在左边还是右边
          const childX = isSrc
            ? parentPosition.x - CONFIG.horizontalGap
            : parentPosition.x + CONFIG.horizontalGap;
          const childY = startY + index * verticalGap;

          // 收集节点
          nodesToAdd.push({
            id: childId,
            x: childX,
            y: childY,
            width: CONFIG.defaultWidth,
            height: CONFIG.defaultHeight,
            shape: 'custom-rect',
            attrs: {
              body: {
                fill: 'var(--color-bg-1)',
              },
              image: {
                'xlink:href': getIconUrl({ icn: '', model_id: child.model_id }),
              },
              tooltip1: {
                text: child.inst_name,
              },
              label1: { text: child.inst_name, title: child.inst_name },
              tooltip2: {
                text: showModelName(child.model_id),
              },
              label2: {
                text: showModelName(child.model_id),
                title: showModelName(child.model_id),
              },
              expandBtnL: {
                stroke: '',
                fill: 'transparent',
                d: getExpandBtnPath(false, false),
              },
              expandBtnR: {
                stroke: child.has_more ? 'var(--color-border-3)' : '',
                fill: child.has_more ? 'var(--color-bg-1)' : 'transparent',
                d: getExpandBtnPath(child.has_more, false),
              },
            },
            data: {
              defaultShow: false,
              expanded: false,
              children: child.children || [],
              modelId: child.model_id,
              inst_name: child.inst_name,
              isSrc: isSrc,
              level: level + 1,
              has_more: child.has_more || false,

            },
          });

          // 收集边端点
          const sourceAnchor = isSrc
            ? { name: 'left', args: { dy: 7 } }  // 左侧节点，从左边连接
            : { name: 'right', args: { dx: 7 } }; // 右侧节点，从右边连接，向下偏移4像素避开按钮(按钮在33.6px，中心在40px，偏移到44px)

          // 回指边的目标锚点：根据目标节点位置设置，避开按钮（按钮在 refY: 0.42，约33.6px）
          // 箭头指向按钮上方（约0.25-0.3位置，即20-24px），避开按钮区域
          const targetAnchor = isSrc
            ? { name: 'left', args: { dy: -10 } }  // 左侧节点，箭头指向左侧，向上偏移避开按钮
            : { name: 'right', args: { dx: 7, dy: -10 } }; // 右侧节点，箭头指向右侧，向上偏移避开按钮

          // 收集边
          edgesToAdd.push(
            isBidirectional
              // 双向边
              ? {
                source: {
                  cell: nodeId,
                  anchor: sourceAnchor,
                },
                target: {
                  cell: childId,
                  anchor: targetAnchor, // 设置目标锚点，让箭头指向按钮上方
                },
                // test6.11双向边使用多段平滑曲线
                connector: {
                  name: 'reverse-curve',
                  args: {
                    curvature: 60,    // 可选：调整弧度大小
                    direction: 'up',  // 可选：'up' 或 'down'
                  }
                },
                attrs: {
                  line: {
                    stroke: 'var(--color-border-3)', strokeWidth: 1
                  },
                },
                label: {
                  attrs: {
                    text: {
                      text: assoTypeList.find((tex) => tex.asst_id === child.asst_id)?.asst_name || '--',
                      fill: 'var(--color-text-4)',
                    },
                    rect: { fill: 'var(--color-bg-1)', stroke: 'none' },
                  },
                },
                router: { name: 'er', args: { direction: 'H', offset: 20 } },
              }
              // 单向边
              : {
                source: {
                  cell: nodeId,
                  anchor: sourceAnchor,
                },
                target: childId,
                // test6.11单向边使用多段平滑曲线
                connector: {
                  name: "normal"
                },
                attrs: {
                  line: {
                    stroke: 'var(--color-border-3)', strokeWidth: 1
                  },
                },
                label: {
                  attrs: {
                    text: {
                      text: assoTypeList.find((tex) => tex.asst_id === child.asst_id)?.asst_name || '--',
                      fill: 'var(--color-text-4)',
                    },
                    rect: { fill: 'var(--color-bg-1)', stroke: 'none' },
                  },
                },
                router: { name: 'er', args: { direction: 'H', offset: 20 } },
              }
          );
        });

        // 一次性添加所有节点和边
        if (nodesToAdd.length > 0 && edgesToAdd.length > 0) {
          // 冻结画布，避免多次渲染
          const graphAny = graph as any;
          if (graphAny && typeof graphAny.freeze === 'function') {
            graphAny.freeze();
          }

          // 添加节点和边
          graph?.addNodes(nodesToAdd);
          graph?.addEdges(edgesToAdd);

          // 解冻画布，触发一次渲染
          if (graphAny && typeof graphAny.unfreeze === 'function') {
            graphAny.unfreeze();
          }

          // 清空节点和边
          nodesToAdd.length = 0;
          edgesToAdd.length = 0;
        }
      }
    }

    // 切换折叠按钮状态
    const btnSelector = isSrcBtn ? 'expandBtnL' : 'expandBtnR';
    node.setAttrs({
      [btnSelector]: {
        d: isExpanded
          ? 'M 3 6 L 9 6 M 6 3 L 6 9 M 1 1 L 11 1 L 11 11 L 1 11 Z'
          : 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z',
      },
    });

    const processChildren = (children: NodeData[], currentLevel: number) => {
      // child_all_predecessors
      // 遍历子节点以显示或隐藏节点
      children.forEach((child: NodeData) => {
        // 获取子节点，并获取子节点的前序节点数组
        const childNode = graph?.getCellById(child._id.toString());
        const child_all_predecessors = graph?.getPredecessors(childNode)?.map((item: any) => item.id);

        // 如果子节点存在，则获取子节点数据
        if (childNode) {
          const childData = childNode.getData();
          const childLevel = childData.level || currentLevel + 1;
          const isSrcNode = childData.isSrc;

          // 如果子节点是源节点，则显示子节点；如果子节点是目标节点，则隐藏子节点；
          if ((isSrcBtn && isSrcNode) || (!isSrcBtn && !isSrcNode)) {
            // 如果当前节点是展开状态，则隐藏子节点；如果当前节点是收起状态，则显示子节点；
            if (isExpanded) {
              // childLevel > currentLevel 说明子节点是父级或祖先，不应该被隐藏

              if (childLevel > currentLevel) {
                childNode.setData({ expanded: false });
                // 隐藏子节点
                if (child_all_predecessors.length > 1) {
                  // 只移除从当前节点指向子节点的边，不隐藏子节点（是移除不是隐藏）
                  const incomingEdges = graph?.getIncomingEdges(childNode);
                  incomingEdges?.forEach((edge: any) => {
                    const sourceCell = edge.getSourceCell();
                    if (sourceCell && sourceCell.id === nodeId) edge.remove();
                  });

                  // 如果当前节点没有任何边则隐藏节点
                  if (incomingEdges?.length === 0) childNode.hide();

                } else {
                  childNode.hide();
                }
                if (childData.children?.length) {
                  processChildren(childData.children, childLevel);
                }
              } else {
                // 如果节点是回环节点，则只隐藏从当前节点指向回环节点的边，不隐藏节点
                const incomingEdges = graph?.getIncomingEdges(childNode);
                if (incomingEdges?.length) {
                  incomingEdges?.forEach((edge: any) => {
                    // 只隐藏从当前节点（node）指向回环节点（childNode）的边
                    const sourceCell = edge.getSourceCell();
                    if (sourceCell && sourceCell.id === nodeId) {
                      edge.hide();
                    }
                  });
                }
              }
            } else {
              // 显示子节点（包括新创建的 level 4及更深层级节点）
              childNode.show();
            }
          }
        }
      });
    };

    const children = node.getData().children || [];
    processChildren(children, level);
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
      inst_name: row.inst_name || '',
    };
    const queryString = new URLSearchParams(params).toString();
    const url = `/cmdb/assetData/detail/baseInfo?${queryString}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const showModelName = (id: string) => {
    return modelList.find((item) => item.model_id === id)?.model_name || '--';
  };

  const getExpandBtnPath = (has_more: boolean, isExpanded: boolean) => {
    if (!has_more) return 'M 3 6 L 9 6 M 1 1 L 11 1 L 11 11 L 1 11 Z';
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
    type: string,
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

    // 注意node对象是Cell对象，不是数据对象
    const id = node._id.toString();
    const has_more = !!node.children?.length;
    const position = nodePositions[id];
    const { hasSrc, hasDst } = layoutInfo;

    if (!position) return;

    const level = Object.keys(levelNodes).find((lvl) =>
      levelNodes[Number(lvl)]?.some((n) => n.id === id)
    );
    const currentLevel = Number(level);
    const isExpanded = currentLevel < CONFIG.maxExpandedLevel;
    const hasLeftBtn = (currentLevel === 1 && hasSrc) || (currentLevel !== 1 && isSrc && has_more)
    const hasRightBtn = (currentLevel === 1 && hasDst) || (currentLevel !== 1 && !isSrc && has_more) || node.has_more;

    nodes.push({
      id,
      x: position.x,
      y: position.y,
      width: CONFIG.defaultWidth,
      height: CONFIG.defaultHeight,
      shape: 'custom-rect',
      attrs: {
        body: {
          // 根节点样式：无背景色，2px蓝色边框，蓝色阴影
          fill: currentLevel === 1 ? 'transparent' : 'var(--color-bg-1)',
          stroke: currentLevel === 1 ? '#0070fa' : undefined,
          strokeWidth: currentLevel === 1 ? 2 : undefined,
          filter: currentLevel === 1 ? 'drop-shadow(0 2px 8px rgba(0, 115, 255, 0.7))' : undefined,
        },
        image: {
          // 根节点图标
          'xlink:href': getIconUrl({ icn: '', model_id: node.model_id }),
          // 根节点图标颜色改为#0070fa（较浅的蓝色）（以后可能有用）
          // filter: currentLevel === 1 ? 'brightness(0) saturate(100%) invert(27%) sepia(96%) saturate(7482%) hue-rotate(210deg) brightness(120%) contrast(90%)' : undefined,
          opacity: currentLevel === 1 ? 0.85 : undefined,
        },
        divider: {
          // 根节点竖线颜色改为#0070fa
          stroke: currentLevel === 1 ? '#0070fa' : undefined,
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
          fill: hasRightBtn ? 'var(--color-bg-1)' : 'transparent',
          d: getExpandBtnPath(hasRightBtn, isExpanded),
        },
      },
      data: {
        defaultShow: currentLevel <= CONFIG.maxExpandedLevel,
        expanded: isExpanded,
        children: has_more ? node.children : [],
        modelId: node.model_id,
        inst_name: node.inst_name,
        isSrc: isSrc,
        level: currentLevel,
        has_more: has_more ? has_more : false,
      },
    });

    // 如果父节点存在且父节点不是回退节点，则创建边
    if (parentId) {
      // type为当前节点类型（src或dst）
      edges.push({
        // 设置源节点和目标节点
        source: type === "src" ? parentId : id,
        target: type === "dst" ? parentId : id,
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
          type,
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

  const transformData = (data: NodeData, type: string, isSrc: boolean, layoutInfo: { hasSrc: boolean; hasDst: boolean }) => {

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
      type,
      data,
      null,
      levelNodes,
      nodePositions,
      isSrc,
      nodes,
      edges,
      layoutInfo
    );

    // nodes, edges是初始化数据处理后的节点和边数据
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
        // 性能优化：使用几何计算而不是 DOM 计算
        useCellGeometry: true,
        // 使用几何计算而不是 DOM 查询，避免性能问题
        boundary: (view: any) => {
          const cell = view.cell;
          const size = cell.getSize();
          // 返回节点的几何边界，使用缓存的大小值，避免 DOM 查询
          return {
            x: 0,
            y: 0,
            width: size.width || CONFIG.defaultWidth,
            height: size.height || CONFIG.defaultHeight,
          };
        },
      },
      true
    );
  };

  return null;
};
