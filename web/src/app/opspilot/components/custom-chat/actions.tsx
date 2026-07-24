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
    <div className={`${styles.operationContainer} ${message.role === 'user' ? 'left' : 'right'}`}>
      <Tooltip title={t('chat.regenerate')}>
        <RedoOutlined className={styles.icon} onClick={() => onRegenerate(message.id)} />
      </Tooltip>
      <Tooltip title={t('common.copy')}>
        <CopyOutlined className={styles.icon} onClick={() => onCopy(message.content)} />
      </Tooltip>
      <MoreActionsDropdown
        items={[
          {
            key: 'regenerate',
            icon: <RedoOutlined />,
            label: t('chat.regenerate'),
            onClick: () => onRegenerate(message.id),
          },
          {
            key: 'copy',
            icon: <CopyOutlined />,
            label: t('common.copy'),
            onClick: () => onCopy(message.content),
          },
          {
            key: 'delete',
            icon: <DeleteOutlined />,
            label: t('common.delete'),
            danger: true,
            onClick: () => onDelete(message.id),
          },
        ]}
        buttonClassName={styles.icon}
      />
    </div>
  );
};

export default MessageActions;
