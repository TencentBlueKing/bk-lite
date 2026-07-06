import React from 'react';
import { Tooltip, Dropdown, Menu } from 'antd';
import { CopyOutlined, RedoOutlined, EllipsisOutlined, DeleteOutlined } from '@ant-design/icons';
import styles from './index.module.scss';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { useTranslation } from '@/utils/i18n';

interface MessageActionsProps {
  message: CustomChatMessage;
  onCopy: (content: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
}

const MessageActions: React.FC<MessageActionsProps> = ({ message, onCopy, onRegenerate, onDelete }) => {
  const { t } = useTranslation();
  const getMenu = (msg: CustomChatMessage) => (
    <Menu>
      <Menu.Item key='regenerate' onClick={() => onRegenerate(msg.id)}>
        <RedoOutlined className='mr-2' /> {t('chat.regenerate')}
      </Menu.Item>
      <Menu.Item key='copy' onClick={() => onCopy(msg.content)}>
        <CopyOutlined className='mr-2' /> {t('common.copy')}
      </Menu.Item>
      <Menu.Item key="delete" onClick={() => onDelete(msg.id)}>
        <DeleteOutlined className='mr-2' /> {t('common.delete')}
      </Menu.Item>
    </Menu>
  );

  return (
    <div className={`${styles.operationContainer} ${message.role === 'user' ? 'left' : 'right'}`}>
      <Tooltip title={t('chat.regenerate')}>
        <RedoOutlined className={styles.icon} onClick={() => onRegenerate(message.id)} />
      </Tooltip>
      <Tooltip title={t('common.copy')}>
        <CopyOutlined className={styles.icon} onClick={() => onCopy(message.content)} />
      </Tooltip>
      <Dropdown overlay={getMenu(message)} trigger={['click']}>
        <Tooltip title={t('common.more')}>
          <EllipsisOutlined className={styles.icon} />
        </Tooltip>
      </Dropdown>
    </div>
  );
};

export default MessageActions;
