import React from 'react';
import { Button, Dropdown, Menu } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import { TableData } from '@/app/opspilot/types/knowledge';
import styles from '@/app/opspilot/styles/common.module.scss';

interface ActionButtonsProps {
  record: TableData;
  isFile?: boolean;
  onTrain: (ids: React.Key[]) => void;
  onDelete: (ids: React.Key[]) => void;
  onSet: (record: any) => void;
  onFileAction: (record: TableData, type: string) => void;
  singleTrainLoading: { [key: string]: boolean };
}

const ActionButtons: React.FC<ActionButtonsProps> = ({
  record,
  isFile,
  onTrain,
  onDelete,
  onSet,
  onFileAction,
  singleTrainLoading,
}) => {
  const { t } = useTranslation();
  const isDisabled = [0, 4].includes(record.train_status);

  const horizontalButtons = (
    <>
      <PermissionWrapper requiredPermissions={['Set']}>
        <Button
          type='link'
          className='mr-[10px]'
          disabled={isDisabled}
          onClick={() => onSet(record)}
        >
          {t('common.set')}
        </Button>
      </PermissionWrapper>
      <PermissionWrapper requiredPermissions={['Train']}>
        <Button
          type='link'
          className='mr-[10px]'
          onClick={() => onTrain([record.id])}
          loading={singleTrainLoading[record.id.toString()]}
          disabled={isDisabled}
        >
          {t('common.train')}
        </Button>
      </PermissionWrapper>
      <PermissionWrapper requiredPermissions={['Delete']}>
        <Button
          type='link'
          onClick={() => onDelete([record.id])}
          disabled={isDisabled}
        >
          {t('common.delete')}
        </Button>
      </PermissionWrapper>
    </>
  );

  const verticalMenuItems = (
    <>
      <Menu.Item key="delete">
        <PermissionWrapper requiredPermissions={['Delete']}>
          <Button
            type="link"
            className="w-full text-left"
            onClick={() => onDelete([record.id])}
            disabled={isDisabled}
          >
            {t('common.delete')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="download">
        <Button
          type='link'
          className="w-full text-left"
          disabled={isDisabled}
          onClick={() => onFileAction(record, 'download')}
        >
          {t('common.download')}
        </Button>
      </Menu.Item>
    </>
  );

  if (!isFile) {
    return horizontalButtons;
  }

  return (
    <>
      <PermissionWrapper requiredPermissions={['Set']}>
        <Button
          type="link"
          className='mr-[10px]'
          disabled={isDisabled}
          onClick={() => onSet(record)}
        >
          {t('common.set')}
        </Button>
      </PermissionWrapper>
      <PermissionWrapper requiredPermissions={['Train']}>
        <Button
          type="link"
          className='mr-[10px]'
          loading={singleTrainLoading[record.id.toString()]}
          disabled={isDisabled}
          onClick={() => onTrain([record.id])}
        >
          {t('common.train')}
        </Button>
      </PermissionWrapper>
      <Button
        type='link'
        className='mr-[10px]'
        disabled={isDisabled}
        onClick={() => onFileAction(record, 'preview')}
      >
        {t('common.preview')}
      </Button>
      <Dropdown
        overlay={
          <Menu className={styles.menuContainer}>
            {verticalMenuItems}
          </Menu>
        }
        trigger={['click']}
      >
        <MoreOutlined className='text-[var(--color-primary)]' />
      </Dropdown>
    </>
  );
};

export default ActionButtons;
