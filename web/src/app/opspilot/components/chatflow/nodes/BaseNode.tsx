'use client';

import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { PlayCircleOutlined } from '@ant-design/icons';
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

  return (
    <div
      className={`${styles.nodeContainer} ${selected ? styles.selected : ''} group relative cursor-pointer`}
      onClick={handleNodeClick}
    >
      {hasInput && (
        <>
          {/* 扩大的透明交互区域 */}
          <div
            className="absolute left-0 top-1/2 -translate-y-1/2 w-6 h-16 -ml-3"
            style={{ 
              zIndex: 999,
              pointerEvents: 'none',
            }}
          />
          <Handle
            type="target"
            position={Position.Left}
            className={`w-2.5 h-2.5 ${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`}
            isConnectable={true}
            isConnectableStart={false}
            isConnectableEnd={true}
            style={{
              width: '16px',
              height: '16px',
              left: '-8px',
            }}
          />
        </>
      )}

      {isTriggerNode && (
        <button
          onClick={handleExecuteClick}
          className="absolute -top-3 -right-3 w-8 h-8 bg-green-500 hover:bg-green-600 rounded-full flex items-center justify-center shadow-lg transition-colors z-10"
          title={t('chatflow.executeNode')}
        >
          <PlayCircleOutlined className="text-white text-xl" />
        </button>
      )}

      <div className={styles.nodeHeader}>
        <Icon type={icon} className={`${styles.nodeIcon} text-${color}-500`} />
        <span className={styles.nodeTitle}>{data.label}</span>
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
          className={`w-2.5 h-2.5 ${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`}
          isConnectable={true}
          isConnectableStart={true}
          isConnectableEnd={false}
          style={{
            width: '14px',
            height: '14px',
            right: '-7px',
          }}
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
                {label && (
                  <span 
                    className="absolute text-xs px-1.5 py-0.5 rounded bg-white/80 font-medium pointer-events-none"
                    style={{ 
                      top: `${topPercent}%`,
                      right: '12px',
                      transform: 'translateY(-50%)',
                      color: colorClass.replace('!bg-', '').replace('-500', ''),
                      fontSize: '10px',
                      lineHeight: '1'
                    }}
                  >
                    {label}
                  </span>
                )}
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
              </React.Fragment>
            );
          })}
        </>
      )}
    </div>
  );
};
