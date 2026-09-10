'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Tooltip } from 'antd';
import { CheckOutlined, CopyOutlined, DeleteOutlined, RedoOutlined } from '@ant-design/icons';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { formatRelativeTime } from '@/app/opspilot/utils/relativeTime';
import { useTranslation } from '@/utils/i18n';

interface MessageActionsProps {
  message: CustomChatMessage;
  onCopy: (content: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
}

const iconBtnClass =
  'flex h-4 w-4 items-center justify-center rounded-sm border-0 bg-transparent p-0 text-[11px] leading-none text-[var(--color-text-3)] hover:bg-[var(--color-fill-2)] hover:text-[var(--color-text-1)] transition-colors cursor-pointer';

const iconStyle = { fontSize: 11 } as const;

const MessageActions: React.FC<MessageActionsProps> = ({ message, onCopy, onRegenerate, onDelete }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isUser = message.role === 'user';
  const timestamp = formatRelativeTime(message.updateAt || message.createAt, t);
  const copyLabel = copied ? t('chat.copied') : t('common.copy');

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    };
  }, []);

  const handleCopy = useCallback(() => {
    onCopy(message.content);
    setCopied(true);
    if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    copiedTimerRef.current = setTimeout(() => setCopied(false), 1600);
  }, [message.content, onCopy]);

  return (
    <div className="inline-flex h-[16px] items-center gap-1">
      <Tooltip title={copyLabel}>
        <button
          type="button"
          onClick={handleCopy}
          className={iconBtnClass}
          aria-label={copyLabel}
        >
          {copied ? (
            <CheckOutlined className="text-[var(--color-success)]" style={iconStyle} />
          ) : (
            <CopyOutlined style={iconStyle} />
          )}
        </button>
      </Tooltip>
      {!isUser && (
        <Tooltip title={t('chat.regenerate')}>
          <button
            type="button"
            onClick={() => onRegenerate(message.id)}
            className={iconBtnClass}
            aria-label={t('chat.regenerate')}
          >
            <RedoOutlined style={iconStyle} />
          </button>
        </Tooltip>
      )}
      <Tooltip title={t('common.delete')}>
        <button
          type="button"
          onClick={() => onDelete(message.id)}
          className={`${iconBtnClass} hover:text-[var(--color-fail)]`}
          aria-label={t('common.delete')}
        >
          <DeleteOutlined style={iconStyle} />
        </button>
      </Tooltip>
      {timestamp ? (
        <span className="ml-1.5 select-none text-[11px] leading-none text-[var(--color-text-4)] tabular-nums">
          {timestamp}
        </span>
      ) : null}
    </div>
  );
};

export default MessageActions;
