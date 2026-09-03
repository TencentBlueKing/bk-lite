import React from 'react';
import { Tooltip } from 'antd';
import { CopyOutlined, RedoOutlined, DeleteOutlined } from '@ant-design/icons';
import styles from './index.module.scss';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { useTranslation } from '@/utils/i18n';
import MoreActionsDropdown from '@/components/more-actions-dropdown';

interface MessageActionsProps {
  message: CustomChatMessage;
  onCopy: (content: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
}

const MessageActions: React.FC<MessageActionsProps> = ({ message, onCopy, onRegenerate, onDelete }) => {
  const { t } = useTranslation();

  return (
    <div className="inline-flex items-center gap-0.5 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] p-0.5 shadow-2xs">
      <Tooltip title={t('chat.regenerate') || '重新生成'}>
        <button
          type="button"
          onClick={() => onRegenerate(message.id)}
          className="flex h-5 w-5 items-center justify-center rounded text-[11px] text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] transition-colors cursor-pointer border-0 bg-transparent"
          aria-label="重新生成"
        >
          <RedoOutlined />
        </button>
      </Tooltip>
      <Tooltip title={t('common.copy') || '复制'}>
        <button
          type="button"
          onClick={() => onCopy(message.content)}
          className="flex h-5 w-5 items-center justify-center rounded text-[11px] text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] transition-colors cursor-pointer border-0 bg-transparent"
          aria-label="复制"
        >
          <CopyOutlined />
        </button>
      </Tooltip>
      <MoreActionsDropdown
        items={[
          {
            key: 'regenerate',
            icon: <RedoOutlined />,
            label: t('chat.regenerate') || '重新生成',
            onClick: () => onRegenerate(message.id),
          },
          {
            key: 'copy',
            icon: <CopyOutlined />,
            label: t('common.copy') || '复制',
            onClick: () => onCopy(message.content),
          },
          {
            key: 'delete',
            icon: <DeleteOutlined />,
            label: t('common.delete') || '删除',
            danger: true,
            onClick: () => onDelete(message.id),
          },
        ]}
        buttonClassName="flex h-5 w-5 items-center justify-center rounded text-[11px] text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] transition-colors border-0 bg-transparent"
      />
    </div>
  );
};

export default MessageActions;
