'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Spin, Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { GraphNode, GraphEdge, GraphData, KnowledgeGraphViewProps } from '@/app/opspilot/types/knowledge';

const generateMockData = (): GraphData => {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  return { nodes, edges };
};

const KnowledgeGraphView: React.FC<KnowledgeGraphViewProps> = ({
  data,
  loading = false,
  height = 500,
  onNodeClick,
  onEdgeClick,
  useMockData = false,
}) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [initError, setInitError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const graphData = useMockData || (!data.nodes.length && !loading) ? generateMockData() : data;

  /**
   * Get node style configuration based on label type
   */
  const getNodeStyle = (type: string) => {
    switch (type) {
      case 'Episodic':
        return { fill: '#B37FEB', stroke: '#9254DE' };
      case 'Entity':
        return { fill: '#FFA940', stroke: '#FA8C16' };
      case 'Community':
        return { fill: '#69C0FF', stroke: '#1890FF' };
      default:
        return { fill: '#C6E5FF', stroke: '#5B8FF9' };
    }
  };

  const getEdgeStyle = (type: string, isSelfLoop: boolean = false) => {
    const baseStyle = {
      stroke: type === 'reference' ? '#999' : '#e2e2e2',
      lineWidth: isSelfLoop ? 3 : 2,
      lineDash: type === 'reference' ? [4, 4] : undefined,
    };
    
    return {
      ...baseStyle,
      endArrow: {
        path: 'M 0,0 L 8,4 L 8,-4 Z',
        fill: baseStyle.stroke,
      },
    };
  };

  const createGraph = async () => {
    if (!containerRef.current || loading || !graphData.nodes.length || graphRef.current) {
      console.log('❌ 跳过图谱创建:', { 
        hasContainer: !!containerRef.current, 
        loading, 
        hasNodes: graphData.nodes.length > 0,
        hasGraph: !!graphRef.current 
      });
      return;
    }

    console.log('🚀 开始创建图谱...', { nodes: graphData.nodes.length, edges: graphData.edges.length });
    setInitError(null);

    try {
      const container = containerRef.current;
      const width = container.offsetWidth || 800;

      const G6Module = await import('@antv/g6');
      const { Graph } = G6Module;

      const truncateText = (text: string, maxLength: number = 8) => {
        if (!text) return '';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
      };

      // 数据校验和去重
      const validNodes = graphData.nodes.filter(node => {
        if (!node.id) {
          console.warn('跳过无效节点（缺少 id）:', node);
          return false;
        }
        return true;
      });

      // 去重节点
      const nodeMap = new Map<string, GraphNode>();
      validNodes.forEach(node => {
        if (!nodeMap.has(String(node.id))) {
          nodeMap.set(String(node.id), node);
        }
      });
      const uniqueNodes = Array.from(nodeMap.values());

      const nodeIdSet = new Set(uniqueNodes.map(node => String(node.id)));

      // 边数据校验
      const validEdges = graphData.edges.filter(edge => {
        if (!edge.source || !edge.target) return false;
        if (!nodeIdSet.has(String(edge.source)) || !nodeIdSet.has(String(edge.target))) return false;
        return true;
      });

      // 去重边数据
      const edgeMap = new Map<string, GraphEdge>();
      validEdges.forEach((edge) => {
        const relationType = edge.relation_type || edge.type || 'default';
        const edgeKey = `${edge.source}-${edge.target}-${edge.label || ''}-${relationType}`;
        if (!edgeMap.has(edgeKey)) {
          edgeMap.set(edgeKey, edge);
        }
      });
      const uniqueEdges = Array.from(edgeMap.values());

      console.log(`✅ 数据校验完成: 节点 ${uniqueNodes.length}, 边 ${uniqueEdges.length}`);

      // 处理节点数据
      const processedNodes = uniqueNodes.map(node => {
        const nodeType = node.labels?.[0] || 'default';
        const style = getNodeStyle(nodeType);
        const displayLabel = truncateText(node.label || node.name || '', 8);

        return {
          id: String(node.id),
          data: {
            label: displayLabel,
            fullLabel: node.label || node.name || '',
            labels: node.labels,
            name: node.name,
            uuid: node.uuid,
            summary: node.summary,
            node_id: node.node_id,
            group_id: node.group_id,
            fact: node.fact,
            nodeType,
            originalFill: style.fill,
            originalStroke: style.stroke,
          },
          style: {
            fill: style.fill,
            stroke: style.stroke,
            lineWidth: 2,
            size: 60,
          },
        };
      });

      // 处理边数据 - 修复G6 5.x兼容性
      const processedEdges = uniqueEdges.map((edge, index) => {
        const isSelfLoop = edge.source === edge.target;
        const style = getEdgeStyle(edge.type || 'relation', isSelfLoop);
        const relationType = edge.relation_type || edge.type || 'default';
        const uniqueEdgeId = `edge-${edge.source}-${edge.target}-${relationType}-${index}`;

        return {
          id: uniqueEdgeId,
          source: String(edge.source),
          target: String(edge.target),
          data: {
            originalId: edge.id,
            label: edge.label,
            edgeType: edge.type,
            relation_type: edge.relation_type,
            source_name: edge.source_name,
            target_name: edge.target_name,
            fact: edge.fact || '-',
            isSelfLoop,
            originalStroke: style.stroke,
          },
          style: {
            stroke: style.stroke,
            lineWidth: style.lineWidth,
            lineDash: style.lineDash,
            endArrow: true, // G6 5.x 中 endArrow 应该是 boolean 类型
          },
        };
      });

      // 初始化 G6 5.x Graph - 使用随机布局算法
      const graph = new Graph({
        container,
        width,
        height,
        data: {
          nodes: processedNodes,
          edges: processedEdges,
        },
        node: {
          type: 'circle',
          style: {
            size: 60,
            labelText: (d: any) => d.data?.label || '',
            labelFill: '#000', // 黑色文字
            labelFontSize: 11,
            labelFontWeight: 500,
            labelX: 0, // 水平偏移为0，在节点中心
            labelY: 0, // 垂直偏移为0，在节点中心
            labelTextAlign: 'center', // 水平居中
            labelTextBaseline: 'middle', // 垂直居中
            labelWordWrap: true,
            labelWordWrapWidth: 50,
            labelMaxLines: 2,
            ports: [],
          },
          state: {
            selected: {
              lineWidth: 4,
              halo: true,
              shadowColor: '#000',
              shadowBlur: 15,
            },
            inactive: {
              opacity: 0.3,
            },
          },
        },
        edge: {
          type: 'line',
          style: {
            labelText: (d: any) => d.data?.label || '',
            labelFill: '#666',
            labelFontSize: 10,
            labelBackground: true,
            labelBackgroundFill: '#fff',
            labelBackgroundOpacity: 0.8,
            labelPadding: [2, 4],
          },
          state: {
            inactive: {
              opacity: 0.2,
            },
          },
        },
        layout: {
          type: 'random', // 使用随机布局，节点随意摆放
          width: width - 30, // 进一步增大布局宽度范围
          height: height - 30, // 进一步增大布局高度范围
          center: [width / 2, height / 2], // 中心点
          preventOverlap: true, // 防止重叠
          nodeSize: 160, // 大幅增加碰撞检测大小，让节点更分散
          maxIterations: 100, // 进一步减少迭代次数，保持更多随机性
        },
        behaviors: [
          'drag-canvas', 
          'zoom-canvas', 
          {
            type: 'drag-element',
            enable: true,
          }
        ],
        autoFit: 'view',
        padding: [80, 80, 80, 80], // 增加更多边距
      });

      await graph.render();
      console.log('✅ 图谱渲染完成');

      // 立即保存graph引用
      graphRef.current = graph;

      // 强制刷新确保节点完全渲染
      setTimeout(() => {
        try {
          // 移除不存在的refresh方法，使用render重新渲染
          graph.render();
          console.log('🔄 强制重新渲染图谱完成');
        } catch (e) {
          console.warn('重新渲染图谱失败:', e);
        }
      }, 100);

      // 立即绑定鼠标悬停事件 - 不使用延迟
      console.log('🔧 立即绑定鼠标悬停事件监听器...');
      
      let currentHoveredNodeId: string | null = null;
      let nodeRelationshipMap: Map<string, string[]> | null = null;
      let isProcessing = false;
      
      // 预计算节点关系映射
      const buildRelationshipMaps = () => {
        if (nodeRelationshipMap) return;
        
        console.log('🚀 构建关系映射...');
        const graphData = graph.getData();
        const edges = graphData.edges || [];
        
        nodeRelationshipMap = new Map();
        
        // 初始化每个节点的关系数组
        graphData.nodes?.forEach(node => {
          nodeRelationshipMap!.set(node.id, [node.id]);
        });
        
        // 建立关系映射
        edges.forEach((edge: any) => {
          const sourceRelations = nodeRelationshipMap!.get(edge.source);
          const targetRelations = nodeRelationshipMap!.get(edge.target);
          
          if (sourceRelations && !sourceRelations.includes(edge.target)) {
            sourceRelations.push(edge.target);
          }
          if (targetRelations && !targetRelations.includes(edge.source)) {
            targetRelations.push(edge.source);
          }
        });
        
        console.log('✅ 关系映射构建完成');
      };
      
      // 立即构建关系映射
      buildRelationshipMaps();
      
      // 鼠标移入节点事件 - 多种事件类型确保兼容性
      const handleNodeHover = (event: any) => {
        if (isProcessing) return;
        
        const nodeId = event.itemId || event.target?.id || event.item?.id || event.id;
        
        if (!nodeId || currentHoveredNodeId === nodeId) {
          return;
        }
        
        console.log('🌟 鼠标移入节点 (立即响应):', nodeId);
        
        isProcessing = true;
        currentHoveredNodeId = nodeId;
        
        try {
          // 获取相关节点
          const relatedNodeIds = nodeRelationshipMap!.get(nodeId) || [nodeId];
          const relatedSet = new Set(relatedNodeIds);
          
          console.log(`📊 相关节点: ${relatedNodeIds.length} 个`);
          
          const graphData = graph.getData();
          const nodeUpdates: any[] = [];
          
          if (graphData.nodes) {
            for (let i = 0; i < graphData.nodes.length; i++) {
              const node = graphData.nodes[i];
              
              if (relatedSet.has(node.id)) {
                // 相关节点：保持原色 - 添加空值检查
                nodeUpdates.push({
                  id: node.id,
                  style: {
                    fill: node.data?.originalFill || '#C6E5FF',
                    stroke: node.data?.originalStroke || '#5B8FF9',
                    opacity: 1,
                    // 当前节点添加阴影
                    ...(node.id === nodeId && {
                      shadowColor: node.data?.originalStroke || '#9254DE',
                      shadowBlur: 15,
                    })
                  },
                });
              } else {
                // 无关节点：置灰
                nodeUpdates.push({
                  id: node.id,
                  style: {
                    fill: '#f5f5f5',
                    stroke: '#d9d9d9',
                    opacity: 0.4,
                  },
                });
              }
            }
          }
          
          // 批量更新节点
          if (nodeUpdates.length > 0) {
            graph.updateNodeData(nodeUpdates);
          }
          
          console.log('✅ 悬停效果完成');
        } catch (error) {
          console.error('❌ 悬停处理错误:', error);
        } finally {
          isProcessing = false;
        }
      };

      // 鼠标移出节点事件
      const handleNodeLeave = () => {
        if (!currentHoveredNodeId || isProcessing) {
          return;
        }
        
        console.log('🌙 鼠标移出节点 (立即重置)');
        
        isProcessing = true;
        currentHoveredNodeId = null;
        
        try {
          const graphData = graph.getData();
          
          if (graphData.nodes) {
            const nodeResets = new Array(graphData.nodes.length);
            
            for (let i = 0; i < graphData.nodes.length; i++) {
              const node = graphData.nodes[i];
              // 修复nodeType类型问题，确保是字符串
              const nodeType = (node.data?.nodeType as string) || 'default';
              const originalStyle = getNodeStyle(nodeType);
              
              nodeResets[i] = {
                id: node.id,
                style: {
                  fill: originalStyle.fill,
                  stroke: originalStyle.stroke,
                  opacity: 1,
                  shadowColor: undefined,
                  shadowBlur: undefined,
                },
              };
            }
            
            graph.updateNodeData(nodeResets);
          }
          
          console.log('✅ 重置完成');
        } catch (error) {
          console.error('❌ 重置错误:', error);
        } finally {
          isProcessing = false;
        }
      };

      // 绑定多种事件类型，确保兼容性
      try {
        graph.on('node:pointerenter', handleNodeHover);
        graph.on('node:pointerleave', handleNodeLeave);
        console.log('✅ 绑定 pointer 事件成功');
      } catch (e) {
        console.warn('pointer 事件绑定失败:', e);
      }
      
      try {
        graph.on('node:mouseenter', handleNodeHover);
        graph.on('node:mouseleave', handleNodeLeave);
        console.log('✅ 绑定 mouse 事件成功');
      } catch (e) {
        console.warn('mouse 事件绑定失败:', e);
      }
      
      try {
        graph.on('node:mouseover', handleNodeHover);
        graph.on('node:mouseout', handleNodeLeave);
        console.log('✅ 绑定 mouseover 事件成功');
      } catch (e) {
        console.warn('mouseover 事件绑定失败:', e);
      }

      // 强制触发一次重绘，确保所有节点都可交互
      setTimeout(() => {
        try {
          console.log('🔄 强制触发重绘确保节点可交互');
          // 使用render方法替代不存在的draw方法
          graph.render();
        } catch (renderError) {
          console.warn('render 方法失败:', renderError);
          // 如果render方法失败，尝试更新数据触发重绘
          try {
            const currentData = graph.getData();
            // 移除不存在的changeData方法，使用setData替代
            graph.setData(currentData);
          } catch (setDataError) {
            console.warn('setData 方法也失败:', setDataError);
          }
        }
      }, 200);

      // 节点拖拽开始事件 - 阻止画布拖拽
      graph.on('node:dragstart', (event: any) => {
        console.log('🖱️ 开始拖拽节点:', event.itemId);
        // 暂时禁用画布拖拽
        graph.setBehaviors([
          'zoom-canvas',
          {
            type: 'drag-element',
            enable: true,
          }
        ]);
      });

      // 节点拖拽结束事件 - 恢复画布拖拽
      graph.on('node:dragend', (event: any) => {
        console.log('🖱️ 结束拖拽节点:', event.itemId);
        // 恢复画布拖拽
        graph.setBehaviors([
          'drag-canvas',
          'zoom-canvas', 
          {
            type: 'drag-element',
            enable: true,
          }
        ]);
      });

      // 节点点击事件 - 修复G6 5.x API
      graph.on('node:click', (event: any) => {
        try {
          const nodeId = event.itemId;
          const nodeModel = graph.getNodeData(nodeId);
          
          if (selectedNodeId === nodeId) {
            setSelectedNodeId(null);
            // 清除选中状态 - 重置所有节点和边样式
            const graphData = graph.getData();
            const allNodes = graphData.nodes || [];
            const allEdges = graphData.edges || [];
            
            allNodes.forEach((node: any) => {
              graph.updateNodeData([{
                id: node.id,
                style: {
                  ...node.style,
                  fill: node.data.originalFill,
                  stroke: node.data.originalStroke,
                  opacity: 1,
                },
              }]);
            });
            
            allEdges.forEach((edge: any) => {
              graph.updateEdgeData([{
                id: edge.id,
                style: {
                  ...edge.style,
                  stroke: edge.data.originalStroke,
                  opacity: 1,
                },
              }]);
            });
          } else {
            setSelectedNodeId(nodeId);
            
            // 查找相关边和节点
            const graphData = graph.getData();
            const allEdges = graphData.edges || [];
            const relatedEdgeIds: string[] = [];
            const relatedNodeIds = new Set([nodeId]);
            
            allEdges.forEach((edge: any) => {
              if (edge.source === nodeId || edge.target === nodeId) {
                relatedEdgeIds.push(edge.id);
                relatedNodeIds.add(edge.source);
                relatedNodeIds.add(edge.target);
              }
            });
            
            // 更新所有节点和边状态
            const allNodes = graphData.nodes || [];
            
            allNodes.forEach((node: any) => {
              if (node.id === nodeId) {
                // 选中节点：高亮显示
                graph.updateNodeData([{
                  id: node.id,
                  style: {
                    ...node.style,
                    lineWidth: 4,
                    shadowColor: node.data.originalStroke,
                    shadowBlur: 15,
                  },
                }]);
              } else if (relatedNodeIds.has(node.id)) {
                // 相关节点：保持原色
                graph.updateNodeData([{
                  id: node.id,
                  style: {
                    ...node.style,
                    fill: node.data.originalFill,
                    stroke: node.data.originalStroke,
                    opacity: 1,
                  },
                }]);
              } else {
                // 无关节点：置灰
                graph.updateNodeData([{
                  id: node.id,
                  style: {
                    ...node.style,
                    fill: '#f5f5f5',
                    stroke: '#d9d9d9',
                    opacity: 0.4,
                  },
                }]);
              }
            });
            
            allEdges.forEach((edge: any) => {
              if (relatedEdgeIds.includes(edge.id)) {
                // 相关边：保持原色
                graph.updateEdgeData([{
                  id: edge.id,
                  style: {
                    ...edge.style,
                    stroke: edge.data.originalStroke,
                    opacity: 1,
                  },
                }]);
              } else {
                // 无关边：置灰
                graph.updateEdgeData([{
                  id: edge.id,
                  style: {
                    ...edge.style,
                    stroke: '#d9d9d9',
                    opacity: 0.3,
                  },
                }]);
              }
            });
          }
          
          // 触发回调
          if (onNodeClick && nodeModel?.data) {
            const data = nodeModel.data as any;
            onNodeClick({
              id: nodeId,
              label: String(data.fullLabel || data.label || ''),
              labels: (data.labels || []) as string[],
              name: String(data.name || ''),
              uuid: String(data.uuid || ''),
              summary: String(data.summary || ''),
              node_id: Number(data.node_id || 0),
              group_id: String(data.group_id || ''),
              fact: String(data.fact || ''),
            });
          }
        } catch (error) {
          console.warn('Error handling node click:', error);
        }
      });

      // 边点击事件 - 修复类型安全
      if (onEdgeClick) {
        graph.on('edge:click', (event: any) => {
          try {
            const edgeId = event.itemId;
            const edgeModel = graph.getEdgeData(edgeId);
            if (edgeModel?.data) {
              const data = edgeModel.data as any;
              onEdgeClick({
                id: String(data.originalId || edgeId),
                source: String(edgeModel.source),
                target: String(edgeModel.target),
                label: String(data.label || ''),
                type: (data.edgeType || 'relation') as 'relation' | 'reference',
                relation_type: String(data.relation_type || ''),
                source_name: String(data.source_name || ''),
                target_name: String(data.target_name || ''),
                fact: String(data.fact || ''),
              });
            }
          } catch (error) {
            console.warn('Error handling edge click:', error);
          }
        });
      }

      // 画布点击事件 - 清除选中状态
      graph.on('canvas:click', () => {
        if (selectedNodeId) {
          setSelectedNodeId(null);
          
          // 重置所有节点和边样式
          const graphData = graph.getData();
          const allNodes = graphData.nodes || [];
          const allEdges = graphData.edges || [];
          
          allNodes.forEach((node: any) => {
            graph.updateNodeData([{
              id: node.id,
              style: {
                ...node.style,
                fill: node.data.originalFill,
                stroke: node.data.originalStroke,
                opacity: 1,
                lineWidth: 2,
                shadowColor: undefined,
                shadowBlur: undefined,
              },
            }]);
          });
          
          allEdges.forEach((edge: any) => {
            graph.updateEdgeData([{
              id: edge.id,
              style: {
                ...edge.style,
                stroke: edge.data.originalStroke,
                opacity: 1,
              },
            }]);
          });
        }
      });
      
    } catch (error) {
      console.error('Failed to create G6 graph:', error);
      setInitError(error instanceof Error ? error.message : 'Unknown error occurred');
    }
  };

  // 数据变化时重新创建图谱
  useEffect(() => {
    // 清理旧图谱
    if (graphRef.current) {
      try {
        graphRef.current.destroy();
      } catch (e) {
        console.warn('Error destroying graph:', e);
      }
      graphRef.current = null;
    }

    // 如果不在加载状态且有数据时才创建图谱
    if (!loading && graphData.nodes.length > 0) {
      // 延时确保容器已渲染
      const timer = setTimeout(() => {
        createGraph();
      }, 200);
      return () => clearTimeout(timer);
    }
  }, [loading, data.nodes.length, data.edges.length]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (graphRef.current) {
        try {
          graphRef.current.destroy();
        } catch (e) {
          console.warn('Error destroying graph on cleanup:', e);
        }
        graphRef.current = null;
      }
    };
  }, []);

  // 窗口大小变化时调整图谱大小
  useEffect(() => {
    const handleResize = () => {
      if (graphRef.current && containerRef.current) {
        try {
          const newWidth = containerRef.current.offsetWidth;
          graphRef.current.setSize(newWidth, height);
        } catch (error) {
          console.warn('Error handling resize:', error);
        }
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [height]);

  // 显示loading状态 - 添加调试日志
  if (loading) {
    console.log('🔄 显示 Loading 状态');
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <Spin size="large" tip={t('knowledge.knowledgeGraph.loading')} />
      </div>
    );
  }

  console.log('📊 准备渲染图表', { hasData: !!graphData.nodes.length, hasError: !!initError });

  if (initError) {
    return (
      <div className="flex flex-col items-center justify-center text-gray-500" style={{ height }}>
        <div className="text-red-500 mb-2">{t('common.initializeFailed')}</div>
        <div className="text-sm">{initError}</div>
        <button 
          className="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          onClick={() => {
            setInitError(null);
            createGraph();
          }}
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  if (!graphData.nodes.length) {
    return (
      <div className="flex items-center justify-center text-gray-500" style={{ height }}>
        <Empty
          description={t('knowledge.knowledgeGraph.noGraphData')}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full border border-gray-200 rounded"
      style={{ height, minHeight: height }}
    />
  );
};

export default KnowledgeGraphView;