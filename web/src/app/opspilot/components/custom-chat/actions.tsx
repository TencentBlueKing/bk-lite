import React from 'react';
import { Tooltip, Dropdown, Menu } from 'antd';
import { CopyOutlined, RedoOutlined, EllipsisOutlined, DeleteOutlined, SignatureFilled } from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import styles from './index.module.scss';
import { CustomChatMessage } from '@/app/opspilot/types/global';
import { useTranslation } from '@/utils/i18n';

interface MessageActionsProps {
  message: CustomChatMessage;
  onCopy: (content: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
  onMark: (msg: CustomChatMessage) => void;
  showMarkOnly?: boolean;
}

const MessageActions: React.FC<MessageActionsProps> = ({ message, onCopy, onRegenerate, onDelete, onMark, showMarkOnly }) => {
  const { t } = useTranslation();
  const getMenu = (msg: CustomChatMessage) => (
    <Menu>
      <Menu.Item key='regenerate' onClick={() => onRegenerate(msg.id)}>
        <RedoOutlined className='mr-2' /> {t('chat.regenerate')}
      </Menu.Item>
      <Menu.Item key='copy' onClick={() => onCopy(msg.content)}>
        <CopyOutlined className='mr-2' /> {t('chat.copy')}
      </Menu.Item>
      {message.role === 'bot' && (<PermissionWrapper className="flex" requiredPermissions={['Mark']}>
        <Menu.Item key="mark" onClick={() => onMark(message)}>
          <SignatureFilled className={`mr-2 ${styles.icon} ${message.annotation ? styles.highlightIcon : ''}`} /> {t('chat.mark')}
        </Menu.Item>
      </PermissionWrapper>)}
      <Menu.Item key="delete" onClick={() => onDelete(msg.id)}>
        <DeleteOutlined className='mr-2' /> {t('common.delete')}
      </Menu.Item>
    </Menu>
  );

  return (
    <div className={`${styles.operationContainer} ${message.role === 'user' ? 'left' : 'right'}`}>
      {showMarkOnly ? (
        (showMarkOnly && message.role === 'bot') ? <Tooltip title={t('chat.mark')}>
          <SignatureFilled className={`${styles.icon} ${message.annotation ? styles.highlightIcon : ''}`} onClick={() => onMark(message)} />
        </Tooltip> : null
      ) : (
        <>
          <Tooltip title={t('chat.regenerate')}>
            <RedoOutlined className={styles.icon} onClick={() => onRegenerate(message.id)} />
          </Tooltip>
          <Tooltip title={t('chat.copy')}>
            <CopyOutlined className={styles.icon} onClick={() => onCopy(message.content)} />
          </Tooltip>
          {message.role === 'bot' ? (<PermissionWrapper
            className="flex"
            requiredPermissions={['Mark']}
            fallback={
              (<span className="flex">
                <SignatureFilled className={`${styles.icon} ${message.annotation ? styles.highlightIcon : ''}`} />
              </span>)
            }
          >
            <Tooltip title={t('chat.mark')}>
              <SignatureFilled className={`${styles.icon} ${message.annotation ? styles.highlightIcon : ''}`} onClick={() => onMark(message)} />
            </Tooltip>
          </PermissionWrapper>) : null}
          <Dropdown overlay={getMenu(message)} trigger={['click']}>
            <Tooltip title={t('chat.more')}>
              <EllipsisOutlined className={styles.icon} />
            </Tooltip>
          </Dropdown>
        </>
      )}
    </div>
  );
};

export default MessageActions;
