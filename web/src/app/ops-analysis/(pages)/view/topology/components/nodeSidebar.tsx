import React, { useEffect } from 'react';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import { SidebarProps, NodeType } from '@/app/ops-analysis/types/topology';
import { Button } from 'antd';
import {
  RightOutlined,
  LeftOutlined,
  AppstoreOutlined,
  AreaChartOutlined,
  BorderOutlined,
  FontSizeOutlined,
} from '@ant-design/icons';

const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  isEditMode = false,
  graphInstance,
  setCollapsed,
  onShowNodeConfig,
  onShowChartSelector,
}) => {
  const { t } = useTranslation();
  const nodeTypes: NodeType[] = [
    {
      id: 'basic-shape',
      name: t('topology.nodeTypes.basicShape'),
      icon: <BorderOutlined className="text-blue-600" />,
    },
    {
      id: 'single-value',
      name: t('topology.nodeTypes.singleValue'),
      icon: (
        <Icon
          type="danzhitu"
          className="text-blue-500"
          style={{ fontSize: '16px' }}
        />
      ),
    },
    {
      id: 'icon',
      name: t('topology.nodeTypes.icon'),
      icon: <AppstoreOutlined className="text-green-500" />,
    },
    {
      id: 'chart',
      name: t('topology.nodeTypes.chart'),
      icon: <AreaChartOutlined className="text-purple-500" />,
    },
    {
      id: 'text',
      name: t('topology.nodeTypes.text'),
      icon: <FontSizeOutlined className="text-orange-500" />,
    },
  ];

  const handleDragStart = (e: React.DragEvent, nodeType: NodeType) => {
    if (!isEditMode) {
      e.preventDefault();
      return;
    }

    e.dataTransfer.setData(
      'application/json',
      JSON.stringify({
        type: 'node',
        nodeTypeId: nodeType.id,
        nodeTypeName: nodeType.name,
      })
    );

    e.dataTransfer.effectAllowed = 'copy';

    // 改进拖拽时的视觉反馈，避免影响原始元素
    if (e.dataTransfer.setDragImage) {
      const dragImage = e.currentTarget.cloneNode(true) as HTMLElement;
      dragImage.style.transform = 'rotate(5deg)';
      dragImage.style.opacity = '0.8';
      dragImage.style.position = 'absolute';
      dragImage.style.top = '-1000px';
      dragImage.style.left = '-1000px';
      dragImage.style.width = '150px';
      dragImage.style.pointerEvents = 'none';

      document.body.appendChild(dragImage);
      e.dataTransfer.setDragImage(dragImage, 75, 20);

      setTimeout(() => {
        if (document.body.contains(dragImage)) {
          document.body.removeChild(dragImage);
        }
      }, 0);
    }
  };

  const handleDragEnd = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleToggleCollapsed = () => {
    setCollapsed(!collapsed);
  };

  useEffect(() => {
    if (isEditMode) {
      setCollapsed(false);
    } else {
      setCollapsed(true);
    }
  }, [isEditMode]);

  // 添加全局拖拽监听器
  useEffect(() => {
    const handleGlobalDrop = (e: DragEvent) => {
      e.preventDefault();

      try {
        const data = e.dataTransfer?.getData('application/json');
        if (data) {
          const dropData = JSON.parse(data);

          if (dropData.type === 'node' && dropData.nodeTypeId) {
            const nodeType = nodeTypes.find(
              (nt) => nt.id === dropData.nodeTypeId
            );

            if (nodeType) {
              let position = { x: e.clientX, y: e.clientY };

              if (graphInstance && 'pageToLocal' in graphInstance) {
                position = (graphInstance as any).pageToLocal(
                  e.clientX,
                  e.clientY
                );
              }

              if (nodeType.id === 'chart') {
                onShowChartSelector?.(position);
              } else if (nodeType.id === 'text') {
                onShowNodeConfig?.(nodeType, position);
                return;
              } else {
                onShowNodeConfig?.(nodeType, position);
              }
            }
          }
        }
      } catch (error) {
        console.error('解析拖拽数据失败:', error);
      }
    };

    const handleGlobalDragOver = (e: DragEvent) => {
      e.preventDefault();
    };

    document.addEventListener('drop', handleGlobalDrop);
    document.addEventListener('dragover', handleGlobalDragOver);

    return () => {
      document.removeEventListener('drop', handleGlobalDrop);
      document.removeEventListener('dragover', handleGlobalDragOver);
    };
  }, [nodeTypes, graphInstance]);

  return (
    <>
      <div
        className={`h-full border-r border-[var(--color-border-1)] bg-[var(--color-fill-1)] transition-[width] duration-300 flex-shrink-0 relative ${
          collapsed ? 'w-0' : 'w-44'
        }`}
      >
        <Button
          type="text"
          icon={collapsed ? <RightOutlined /> : <LeftOutlined />}
          onClick={handleToggleCollapsed}
          className="absolute top-5 bg-[var(--color-bg-1)] rounded-full shadow-sm border border-[var(--color-border-1)] hover:border-blue-300 !p-0"
          style={{
            width: '24px',
            height: '24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 0,
            zIndex: 10,
            right: collapsed ? '-24px' : '-12px',
            borderRadius: collapsed ? '0 50% 50% 0' : '50%',
          }}
        />

        {!collapsed && (
          <div className="h-full p-4 opacity-100 transition-opacity duration-300">
            <div className="h-full overflow-auto">
              <div className="space-y-3">
                {nodeTypes.map((nodeType) => (
                  <div
                    key={nodeType.id}
                    className={`px-2 py-1.5 rounded-lg transition-all duration-200 bg-[var(--color-bg-1)] ${
                      isEditMode
                        ? 'cursor-grab active:cursor-grabbing'
                        : 'cursor-not-allowed'
                    }`}
                    draggable={isEditMode}
                    onDragStart={(e) => handleDragStart(e, nodeType)}
                    onDragEnd={handleDragEnd}
                  >
                    <div className="flex items-center space-x-3">
                      <div>{nodeType.icon}</div>
                      <div className="flex-1 text-[var(--color-text-2)]">
                        {nodeType.name}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default Sidebar;
