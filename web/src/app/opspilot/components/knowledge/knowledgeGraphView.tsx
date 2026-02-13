'use client';
import React, { useEffect, useRef, useState } from 'react';
import { Spin, Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { GraphNode, GraphEdge, GraphData, KnowledgeGraphViewProps } from '@/app/opspilot/types/knowledge';

const generateMockData = (): GraphData => {
  const nodes: GraphNode[] = [
    // { id: '1', label: 'DevOps工作流', labels: ['Episodic'] },
  ];

  const edges: GraphEdge[] = [
    // { id: 'e1', source: '1', target: '2', label: '包含', type: 'relation' },
  ];

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
  const [isInitializing, setIsInitializing] = useState(false);
  const [containerHeight, setContainerHeight] = useState<number | string>(height);

  const graphData = useMockData || (!data.nodes.length && !loading) ? generateMockData() : data;

  useEffect(() => {
    if (height === '100%' && containerRef.current) {
      const updateHeight = () => {
        const parentHeight = containerRef.current?.parentElement?.clientHeight;
        if (parentHeight) {
          setContainerHeight(parentHeight);
        }
      };
      updateHeight();
      window.addEventListener('resize', updateHeight);
      return () => window.removeEventListener('resize', updateHeight);
    } else {
      setContainerHeight(height);
    }
  }, [height]);

  /**
   * Get node style configuration based on label type
   * - Episodic: Purple color scheme
   * - Entity: Orange color scheme  
   * - Group: Blue color scheme
   */
  const getNodeStyle = (type: string) => {
    switch (type) {
      case 'Episodic':
        return {
          fill: '#B37FEB',
          stroke: '#9254DE',
          size: 40,
        };
      case 'Entity':
        return {
          fill: '#FFA940',
          stroke: '#FA8C16',
          size: 40,
        };
      case 'Community':
        return {
          fill: '#69C0FF',
          stroke: '#1890FF',
          size: 40,
        };
      default:
        return {
          fill: '#C6E5FF',
          stroke: '#5B8FF9',
          size: 40,
        };
    }
  };

  const getEdgeStyle = (type: string, isSelfLoop: boolean = false) => {
    if (isSelfLoop) {
      return {
        stroke: type === 'reference' ? '#999' : '#e2e2e2',
        lineWidth: 3,
        lineDash: type === 'reference' ? [4, 4] : undefined,
        endArrow: {
          path: 'M 0,0 L 8,4 L 8,-4 Z',
          fill: type === 'reference' ? '#999' : '#e2e2e2',
          stroke: type === 'reference' ? '#999' : '#e2e2e2',
        },
      };
    }

    switch (type) {
      case 'reference':
        return {
          stroke: '#999',
          lineDash: [4, 4],
          lineWidth: 2,
          endArrow: {
            path: 'M 0,0 L 8,4 L 8,-4 Z',
            fill: '#999',
            stroke: '#999',
          },
        };
      default:
        return {
          stroke: '#e2e2e2',
          lineWidth: 2,
          endArrow: {
            path: 'M 0,0 L 8,4 L 8,-4 Z',
            fill: '#e2e2e2',
            stroke: '#e2e2e2',
          },
        };
    }
  };

  const createGraph = async () => {
    if (!containerRef.current || loading || !graphData.nodes.length || isInitializing || graphRef.current) {
      return;
    }

    setIsInitializing(true);
    setInitError(null);

    try {
      const container = containerRef.current;
      const width = container.offsetWidth || 800;

      const G6Module = await import('@antv/g6');
      const G6 = G6Module.default || G6Module;
      
      if (!G6 || !G6.Graph) {
        throw new Error('G6 Graph constructor not found');
      }

      const actualHeight = container.offsetHeight;

      const truncateText = (text: string, maxLength: number = 3) => {
        if (!text) return '';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
      };

      // 为G6 v5准备数据 - 将样式属性直接放在data中
      const formattedData = {
        nodes: graphData.nodes.map(node => {
          const nodeType = node.labels && node.labels.length > 0 ? node.labels[0] : 'default';
          const nodeStyle = getNodeStyle(nodeType);
          const displayLabel = truncateText(node.label || node.name || '', 3);

          return {
            id: node.id,
            data: {
              type: 'circle-node',
              // 样式属性
              fill: nodeStyle.fill,
              stroke: nodeStyle.stroke,
              lineWidth: 2,
              // 额外数据
              label: displayLabel,
              fullLabel: node.label || node.name || '',
              labels: node.labels,
              name: node.name,
              uuid: node.uuid,
              summary: node.summary,
              node_id: node.node_id,
              group_id: node.group_id,
              fact: node.fact,
            },
          };
        }),
        edges: graphData.edges.map((edge) => {
          const edgeStyle = getEdgeStyle(edge.type, false);

          return {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            data: {
              type: 'line-edge',
              // 样式属性
              stroke: edgeStyle.stroke,
              lineWidth: edgeStyle.lineWidth,
              // 额外数据
              label: edge.label,
              source_name: edge.source_name,
              target_name: edge.target_name,
              fact: edge.fact || '-',
              relation_type: edge.relation_type,
            },
          };
        }),
      };

      // Initialize G6 v5 Graph
      const graph = new G6.Graph({
        container: container,
        width,
        height: actualHeight,
        data: formattedData,
        layout: {
          type: 'force',
          preventOverlap: true,
          linkDistance: 180,
        },
        theme: 'light',
        node: {
          style: {
            size: 60,
            fill: (d: any) => d.data.fill || '#C6E5FF',
            stroke: (d: any) => d.data.stroke || '#5B8FF9',
            lineWidth: (d: any) => d.data.lineWidth || 2,
            opacity: (d: any) => d.data.opacity !== undefined ? d.data.opacity : 1,
            shadowColor: (d: any) => d.data.shadowColor,
            shadowBlur: (d: any) => d.data.shadowBlur || 0,
            labelText: (d: any) => d.data.label || '',
            labelPlacement: 'center',
            labelFill: '#fff',
            labelFontSize: 11,
            labelFontWeight: 500,
          },
        },
        edge: {
          style: {
            stroke: (d: any) => d.data.stroke || '#e2e2e2',
            lineWidth: (d: any) => d.data.lineWidth || 2,
            opacity: (d: any) => d.data.opacity !== undefined ? d.data.opacity : 1,
            endArrow: true,
            labelText: (d: any) => d.data.label || '',
            labelPlacement: 'center',
            labelFill: '#666',
            labelFontSize: 10,
            labelBackground: true,
            labelBackgroundFill: '#fff',
            labelBackgroundOpacity: 0.8,
            labelPadding: [2, 4],
          },
        },
        behaviors: [
          'drag-canvas', 
          'zoom-canvas', 
          'drag-element',
          { type: 'hover-activate', degree: 1 }
        ],
        autoFit: 'view',
      } as any);
      
      // 渲染图谱
      await graph.render();

      if (onNodeClick) {
        graph.on('node:click', (event: any) => {
          try {
            // G6 v5 事件对象结构
            const nodeData = event.target?.id ? graph.getNodeData(event.target.id) : null;
            if (nodeData && nodeData.data) {
              const data = nodeData.data as any;
              onNodeClick({
                id: nodeData.id as string,
                label: data.fullLabel || data.label || '',
                labels: data.labels || [],
                name: data.name || '',
                uuid: data.uuid || '',
                summary: data.summary || '',
                node_id: data.node_id || 0,
                group_id: data.group_id || '',
                fact: data.fact || '',
              });
            }
          } catch (error) {
            console.error('Error handling node click:', error);
          }
        });
      }

      if (onEdgeClick) {
        graph.on('edge:click', (event: any) => {
          try {
            // G6 v5 事件对象结构
            const edgeData = event.target?.id ? graph.getEdgeData(event.target.id) : null;
            if (edgeData && edgeData.data) {
              const data = edgeData.data as any;
              onEdgeClick({
                id: edgeData.id as string,
                source: edgeData.source as string,
                target: edgeData.target as string,
                label: data.label || '',
                type: 'relation' as 'relation' | 'reference',
                source_name: data.source_name || '',
                target_name: data.target_name || '',
                fact: data.fact || null,
              });
            }
          } catch (error) {
            console.error('Error handling edge click:', error);
          }
        });
      }

      // 鼠标移入节点时，高亮相关节点和边 - 参考 v4 逻辑用 v5 API 实现
      let currentHoverNodeId: string | null = null;

      graph.on('afterrender', () => {});

      graph.on('node:pointerenter', (event: any) => {
        try {
          // v5 中尝试多种方式获取节点ID
          const nodeId = event.itemId || event.target?.id || event.target?.cfg?.id || (event.item && event.item.id);
          
          if (!nodeId) {
            return;
          }

          // 如果是同一个节点，不重复处理
          if (currentHoverNodeId === nodeId) return;
          
          currentHoverNodeId = nodeId;
          const allNodes = graph.getData().nodes || [];
          const allEdges = graph.getData().edges || [];
          
          const relatedNodeIds = new Set([nodeId]);
          const relatedEdgeIds = new Set<string>();
          
          allEdges.forEach((edge: any) => {
            if (edge.source === nodeId || edge.target === nodeId) {
              relatedEdgeIds.add(edge.id);
              relatedNodeIds.add(edge.source);
              relatedNodeIds.add(edge.target);
            }
          });
          
          const nodeUpdates = allNodes.map((node: any) => {
            const isRelated = relatedNodeIds.has(node.id);
            const nodeData = graph.getNodeData(node.id);
            const data = nodeData?.data as any;
            const nodeType = data?.labels && data.labels.length > 0 
              ? data.labels[0] 
              : 'default';
            const originalStyle = getNodeStyle(nodeType);
                
            if (node.id === nodeId) {
              return {
                id: node.id,
                data: {
                  ...data,
                  fill: originalStyle.fill,
                  stroke: originalStyle.stroke,
                  lineWidth: 3,
                  shadowColor: '#000',
                  shadowBlur: 10,
                  opacity: 1,
                }
              };
            } else if (isRelated) {
              return {
                id: node.id,
                data: {
                  ...data,
                  fill: originalStyle.fill,
                  stroke: originalStyle.stroke,
                  lineWidth: 3,
                  opacity: 1,
                  shadowColor: undefined,
                  shadowBlur: undefined,
                }
              };
            } else {
              return {
                id: node.id,
                data: {
                  ...data,
                  fill: '#e8e8e8',
                  stroke: '#d0d0d0',
                  lineWidth: 1,
                  opacity: 0.4,
                  shadowColor: undefined,
                  shadowBlur: undefined,
                }
              };
            }
          });
              
          graph.updateNodeData(nodeUpdates);
          graph.draw();
              
          const edgeUpdates = allEdges.map((edge: any) => {
            const isRelated = relatedEdgeIds.has(edge.id);
            const edgeData = graph.getEdgeData(edge.id);
            const data = edgeData?.data as any;
                
            if (isRelated) {
              const edgeType = (data?.relation_type as string) || 'relation';
              const originalStyle = getEdgeStyle(edgeType, false);
              return {
                id: edge.id,
                data: {
                  ...data,
                  stroke: originalStyle.stroke,
                  lineWidth: 3,
                  opacity: 1,
                }
              };
            } else {
              return {
                id: edge.id,
                data: {
                  ...data,
                  stroke: '#d9d9d9',
                  lineWidth: 1,
                  opacity: 0.2,
                }
              };
            }
          });
          
          graph.updateEdgeData(edgeUpdates);
          graph.draw();
        } catch (error) {
          console.error('Error handling node pointerenter:', error);
        }
      });

      graph.on('node:pointerleave', () => {
        try {
          currentHoverNodeId = null;
          const allNodes = graph.getData().nodes || [];
          const allEdges = graph.getData().edges || [];
          
          const nodeUpdates = allNodes.map((node: any) => {
            const nodeData = graph.getNodeData(node.id);
            const data = nodeData?.data as any;
            const nodeType = data?.labels && data.labels.length > 0 
              ? data.labels[0] 
              : 'default';
            const originalStyle = getNodeStyle(nodeType);
            
            return {
              id: node.id,
              data: {
                ...data,
                fill: originalStyle.fill,
                stroke: originalStyle.stroke,
                lineWidth: 2,
                opacity: 1,
                shadowColor: undefined,
                shadowBlur: undefined,
              }
            };
          });
          
          graph.updateNodeData(nodeUpdates);
          graph.draw();
          
          const edgeUpdates = allEdges.map((edge: any) => {
            const edgeData = graph.getEdgeData(edge.id);
            const data = edgeData?.data as any;
            const edgeType = (data?.relation_type as string) || 'relation';
            const originalStyle = getEdgeStyle(edgeType, false);
            
            return {
              id: edge.id,
              data: {
                ...data,
                stroke: originalStyle.stroke,
                lineWidth: originalStyle.lineWidth,
                opacity: 1,
              }
            };
          });
          
          graph.updateEdgeData(edgeUpdates);
          // 强制重新渲染
          graph.draw();
        } catch (error) {
          console.error('Error handling node pointerleave:', error);
        }
      });

      graphRef.current = graph;
      
    } catch (error) {
      console.error('Failed to create G6 graph:', error);
      setInitError(error instanceof Error ? error.message : 'Unknown error occurred');
    } finally {
      setIsInitializing(false);
    }
  };

  useEffect(() => {
    if (!graphRef.current && !loading && graphData.nodes.length > 0) {
      const timer = setTimeout(() => {
        createGraph();
      }, 100);

      return () => clearTimeout(timer);
    }
  }, [useMockData, containerHeight]);

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

  useEffect(() => {
    const handleResize = () => {
      if (graphRef.current && containerRef.current) {
        try {
          const newWidth = containerRef.current.offsetWidth;
          const newHeight = typeof containerHeight === 'number' ? containerHeight : containerRef.current.offsetHeight || 500;
          graphRef.current.changeSize(newWidth, newHeight);
        } catch (error) {
          console.warn('Error handling resize:', error);
        }
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [containerHeight]);

  if (loading || isInitializing) {
    return (
      <div className="flex items-center justify-center" style={{ height: containerHeight }}>
        <Spin size="large" tip={t('knowledge.knowledgeGraph.loading')} />
      </div>
    );
  }

  if (initError) {
    return (
      <div className="flex flex-col items-center justify-center text-gray-500" style={{ height: containerHeight }}>
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
      <div className="flex items-center justify-center text-gray-500" style={{ height: containerHeight }}>
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
      style={{ height: '100%' }}
    />
  );
};

export default KnowledgeGraphView;