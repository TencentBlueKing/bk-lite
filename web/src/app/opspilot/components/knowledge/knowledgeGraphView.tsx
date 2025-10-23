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

  const graphData = useMockData || (!data.nodes.length && !loading) ? generateMockData() : data;

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

      const truncateText = (text: string, maxLength: number = 3) => {
        if (!text) return '';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
      };

      const processedData = {
        nodes: graphData.nodes.map(node => {
          const nodeType = node.labels && node.labels.length > 0 ? node.labels[0] : 'default';
          const style = getNodeStyle(nodeType);
          const displayLabel = truncateText(node.label || node.name || '', 3);

          return {
            id: node.id,
            label: displayLabel,
            labels: node.labels,
            name: node.name,
            uuid: node.uuid,
            summary: node.summary,
            node_id: node.node_id,
            group_id: node.group_id,
            fact: node.fact,
            size: 60,
            style: {
              fill: style.fill,
              stroke: style.stroke,
              lineWidth: 2,
            },
          };
        }),
        edges: graphData.edges.map((edge, index) => {
          const isSelfLoop = edge.source === edge.target;
          const style = getEdgeStyle(edge.type, isSelfLoop);

          const loopPositions = ['top', 'top-right', 'right', 'bottom-right', 'bottom', 'bottom-left', 'left', 'top-left'];
          const loopIndex = index % loopPositions.length;

          return {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.label,
            type: isSelfLoop ? 'loop' : 'line',
            source_name: edge.source_name,
            target_name: edge.target_name,
            fact: edge.fact || '-',
            style: {
              stroke: style.stroke,
              lineWidth: style.lineWidth,
              ...(style.lineDash && { lineDash: style.lineDash }),
              endArrow: style.endArrow,
            },
            ...(isSelfLoop && {
              loopCfg: {
                position: loopPositions[loopIndex],
                dist: 60 + (loopIndex * 10),
                clockwise: index % 2 === 0,
              }
            }),
          };
        }),
      };

      // Initialize G6 Graph with TypeScript assertion for API compatibility
      const graph = new G6.Graph({
        container: container,
        width,
        height,
        layout: {
          type: 'force',
          preventOverlap: true,
          nodeSize: 60, // Update to match actual node size
          linkDistance: 180, // Increase link distance to give nodes more space
          nodeStrength: -150, // Enhance node repulsion to avoid overlap
          edgeStrength: 0.8,
          gravity: 0.1,
        },
        defaultNode: {
          type: 'circle',
          size: 60, // Increase node size to provide more space for text
          labelCfg: {
            position: 'center',
            style: {
              fontSize: 11,
              fill: '#333', // Change to dark gray for better readability
              fontWeight: '500', // Slightly reduce font weight
              textAlign: 'center',
              textBaseline: 'middle',
              wordWrap: true, // Enable text wrapping
              wordWrapWidth: 50, // Set wrap width
            },
          },
          style: {
            lineWidth: 2,
            stroke: '#5B8FF9',
            fill: '#C6E5FF',
          },
          stateStyles: {
            hover: {
              lineWidth: 4,
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowOffsetY: 0,
            },
            highlight: {
              lineWidth: 3,
              opacity: 1,
            },
            inactive: {
              opacity: 0.3,
            },
          },
        },
        defaultEdge: {
          type: 'line',
          labelCfg: {
            autoRotate: true,
            style: {
              fontSize: 10,
              fill: '#666',
            },
          },
          style: {
            stroke: '#e2e2e2',
            lineWidth: 2,
            endArrow: {
              path: 'M 0,0 L 8,4 L 8,-4 Z',
              fill: '#e2e2e2',
              stroke: '#e2e2e2',
            },
          },
          stateStyles: {
            highlight: {
              lineWidth: 3,
              opacity: 1,
            },
            inactive: {
              opacity: 0.2,
            },
          },
        },
        modes: {
          default: [
            'drag-canvas',
            'zoom-canvas',
            'drag-node',
            'click-select',
          ],
        },
        fitView: true,
        fitViewPadding: 20,
      } as any);

      // Bind data and render graph
      (graph as any).data(processedData);
      (graph as any).render();

      if (onNodeClick) {
        graph.on('node:click', (event: any) => {
          try {
            const node = event.item;
            const model = node.getModel();
            if (model) {
              onNodeClick({
                id: model.id as string,
                label: model.label as string,
                labels: model.labels as string[],
                name: model.name as string,
                uuid: model.uuid as string,
                summary: model.summary as string,
                node_id: model.node_id as number,
                group_id: model.group_id as string,
                fact: model.fact as string,
              });
            }
          } catch (error) {
            console.warn('Error handling node click:', error);
          }
        });
      }

      if (onEdgeClick) {
        graph.on('edge:click', (event: any) => {
          try {
            const edge = event.item;
            const model = edge.getModel();
            if (model) {
              onEdgeClick({
                id: model.id as string,
                source: model.source as string,
                target: model.target as string,
                label: model.label as string,
                type: model.type as 'relation' | 'reference',
                source_name: model.source_name as string,
                target_name: model.target_name as string,
                fact: model.fact as string | null,
              });
            }
          } catch (error) {
            console.warn('Error handling edge click:', error);
          }
        });
      }

      /**
       * Enhanced hover effect with dynamic shadow colors
       * - Current node: 4px border + matching shadow color
       * - Related nodes: Keep original colors with thicker border  
       * - Unrelated nodes: Reduced opacity
       */
      graph.on('node:mouseenter', (event: any) => {
        try {
          const node = event.item;
          const nodeModel = node.getModel();
          const nodeId = nodeModel.id;
          
          // Set dynamic shadow color based on node's original stroke color
          const shadowColor = nodeModel.style.stroke || '#9254DE';
          
          (graph as any).updateItem(node, {
            style: {
              ...nodeModel.style,
              lineWidth: 4,
              shadowColor: shadowColor,
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowOffsetY: 0,
            },
          });
          
          const edges = (graph as any).getEdges();
          const nodes = (graph as any).getNodes();
          
          // Find related edges and nodes
          const relatedEdges: any[] = [];
          const relatedNodeIds = new Set([nodeId]);
          
          edges.forEach((edge: any) => {
            const edgeModel = edge.getModel();
            if (edgeModel.source === nodeId || edgeModel.target === nodeId) {
              relatedEdges.push(edge);
              relatedNodeIds.add(edgeModel.source);
              relatedNodeIds.add(edgeModel.target);
            }
          });
          
          // Update edge states
          edges.forEach((edge: any) => {
            if (relatedEdges.includes(edge)) {
              (graph as any).setItemState(edge, 'highlight', true);
            } else {
              (graph as any).setItemState(edge, 'inactive', true);
            }
          });
          
          // Update node states - keep original colors for related nodes
          nodes.forEach((n: any) => {
            const nModel = n.getModel();
            if (nModel.id !== nodeId) {
              if (relatedNodeIds.has(nModel.id)) {
                // Related nodes: preserve original colors, only increase border width
                (graph as any).updateItem(n, {
                  style: {
                    ...nModel.style,
                    lineWidth: 3,
                    opacity: 1,
                  },
                });
              } else {
                (graph as any).setItemState(n, 'inactive', true);
              }
            }
          });
        } catch (error) {
          console.warn('Error handling node mouseenter:', error);
        }
      });

      // Reset all styles when mouse leaves node
      graph.on('node:mouseleave', () => {
        try {
          const nodes = (graph as any).getNodes();
          const edges = (graph as any).getEdges();
          
          nodes.forEach((node: any) => {
            const nodeModel = node.getModel();
            (graph as any).clearItemStates(node);
            (graph as any).updateItem(node, {
              style: {
                ...nodeModel.style,
                lineWidth: 2,
                shadowColor: undefined,
                shadowBlur: undefined,
                shadowOffsetX: undefined,
                shadowOffsetY: undefined,
                opacity: 1,
              },
            });
          });
          
          edges.forEach((edge: any) => {
            (graph as any).clearItemStates(edge);
          });
        } catch (error) {
          console.warn('Error handling node mouseleave:', error);
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
  }, [useMockData]);

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
          graphRef.current.changeSize(newWidth, height);
        } catch (error) {
          console.warn('Error handling resize:', error);
        }
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [height]);

  if (loading || isInitializing) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <Spin size="large" tip={t('knowledge.knowledgeGraph.loading')} />
      </div>
    );
  }

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