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
  hasMultipleOutputs = false
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
        <Handle
          type="target"
          position={Position.Left}
          className={`w-2.5 h-2.5 ${handleColorClasses[color as keyof typeof handleColorClasses] || handleColorClasses.blue} !border-2 !border-white shadow-md`}
        />
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
        />
      )}

      {hasMultipleOutputs && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            className="w-2.5 h-2.5 !bg-green-500 !border-2 !border-white shadow-md"
            id="true"
            style={{ top: '30%' }}
          />
          <Handle
            type="source"
            position={Position.Right}
            className="w-2.5 h-2.5 !bg-red-500 !border-2 !border-white shadow-md"
            id="false"
            style={{ top: '70%' }}
          />
        </>
      )}
    </div>
  );
};
