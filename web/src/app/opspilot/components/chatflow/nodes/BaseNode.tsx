'use client';

import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { PlayCircleOutlined, CloseOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import type { ChatflowNodeData } from '../types';
import { handleColorClasses, TRIGGER_NODE_TYPES } from '@/app/opspilot/constants/chatflow';
import { formatConfigInfo } from '../utils/formatConfigInfo';
import styles from '../ChatflowEditor.module.scss';

interface BaseNodeProps {
  data: ChatflowNodeData;
  id: string;
  selected?: boolean;
  onConfig: (id: string) => void;
  onDelete?: (id: string) => void;
  icon: string;
  color?: string;
  hasInput?: boolean;
  hasOutput?: boolean;
  hasMultipleOutputs?: boolean;
  multipleOutputsCount?: number;
  outputLabels?: string[];
  outputHandleIds?: string[]; // 自定义的 Handle ID 列表
}

export const BaseNode = ({
  data,
  id,
  selected,
  onConfig,
  onDelete,
  icon,
  color = 'blue',
  hasInput = false,
  hasOutput = true,
  hasMultipleOutputs = false,
  outputLabels = [],
  multipleOutputsCount = 2,
  outputHandleIds = []
}: BaseNodeProps) => {
  const { t } = useTranslation();

  const handleNodeClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onConfig(id);
  };

  const isTriggerNode = TRIGGER_NODE_TYPES.includes(data.type as any);

  const handleExecuteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const event = new CustomEvent('executeNode', {
      detail: { nodeId: id, nodeType: data.type }
    });
    window.dispatchEvent(event);
  };

  const handleDeleteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onDelete?.(id);
  };

  return (
    <div
      className={`${styles.nodeContainer} ${selected ? styles.selected : ''} group relative cursor-pointer`}
      onClick={handleNodeClick}
    >
      {hasInput && (
        <Handle
          type="target"
          position={Position.Left}
          className={`${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`}
          isConnectable={true}
          isConnectableStart={false}
          isConnectableEnd={true}
        />
      )}

      <button
        onClick={handleDeleteClick}
        className="absolute -top-3 -right-3 w-6 h-6 bg-[#3d3d3d] hover:bg-red-500 rounded-full flex items-center justify-center shadow-lg transition-all z-20 opacity-0 group-hover:opacity-100"
        title={t('common.delete')}
      >
        <CloseOutlined className="text-white text-sm" />
      </button>

      <div className={styles.nodeHeader}>
        <Icon type={icon} className={`${styles.nodeIcon} text-${color}-500`} />
        <span className={styles.nodeTitle}>{data.label}</span>
        {isTriggerNode && (
          <button
            onClick={handleExecuteClick}
            className="ml-auto w-6 h-6 text-green-500 hover:text-green-400 flex items-center justify-center transition-colors"
            title={t('chatflow.executeNode')}
          >
            <PlayCircleOutlined className="text-lg" />
          </button>
        )}
      </div>

      <div className={styles.nodeContent}>
        <div className={styles.nodeConfigInfo}>
          {formatConfigInfo(data, t)}
        </div>
        {data.description && (
          <p className={styles.nodeDescription}>
            {data.description}
          </p>
        )}
      </div>

      {hasOutput && !hasMultipleOutputs && (
        <Handle
          type="source"
          position={Position.Right}
          className={`${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`}
          isConnectable={true}
          isConnectableStart={true}
          isConnectableEnd={false}
        />
      )}

      {hasMultipleOutputs && (
        <>
          {Array.from({ length: multipleOutputsCount }).map((_, index) => {
            const total = multipleOutputsCount;
            const topPercent = ((index + 1) / (total + 1)) * 100;
            const colors = ['!bg-blue-500', '!bg-green-500', '!bg-purple-500', '!bg-orange-500', '!bg-pink-500', '!bg-cyan-500'];
            const colorClass = colors[index % colors.length];
            const label = outputLabels[index] || `${index + 1}`;
            // 使用自定义 Handle ID，如果没有则使用默认的 output-{index}
            const handleId = outputHandleIds[index] || `output-${index}`;
            
            return (
              <React.Fragment key={handleId}>
                <Handle
                  key={`handle-${handleId}`}
                  type="source"
                  position={Position.Right}
                  id={handleId}
                  className={`${colorClass} !border-2 !border-white shadow-md`}
                  style={{ 
                    top: `${topPercent}%`,
                    transform: 'translateY(-50%)',
                    width: '14px',
                    height: '14px',
                    right: '-7px',
                  }}
                  isConnectable={true}
                  isConnectableStart={true}
                  isConnectableEnd={false}
                />
                {label && (
                  <span 
                    className="absolute text-xs px-2 py-1 rounded bg-white shadow-sm border border-gray-200 font-medium pointer-events-none whitespace-nowrap"
                    style={{ 
                      top: `${topPercent}%`,
                      left: '100%',
                      marginLeft: '8px',
                      transform: 'translateY(-50%)',
                      color: colorClass.replace('!bg-', '').replace('-500', ''),
                      fontSize: '11px',
                      lineHeight: '1',
                      zIndex: 10,
                    }}
                  >
                    {label}
                  </span>
                )}
              </React.Fragment>
            );
          })}
        </>
      )}
    </div>
  );
};
