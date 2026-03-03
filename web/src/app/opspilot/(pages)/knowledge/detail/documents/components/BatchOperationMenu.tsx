'use client';

import React from 'react';
import { Button, Menu, Dropdown, Space } from 'antd';
import { DeleteOutlined, TrademarkOutlined, DownOutlined } from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import styles from '@/app/opspilot/styles/common.module.scss';

interface BatchOperationMenuProps {
  selectedRowKeys: React.Key[];
  permissions: string[];
  isTrainLoading: boolean;
  onTrain: (keys: React.Key[]) => void;
  onDelete: (keys: React.Key[]) => void;
  onBatchSet: (keys: React.Key[]) => void;
  t: (key: string) => string;
}

const BatchOperationMenu: React.FC<BatchOperationMenuProps> = ({
  selectedRowKeys,
  permissions,
  isTrainLoading,
  onTrain,
  onDelete,
  onBatchSet,
  t,
}) => {
  const menu = (
    <Menu className={styles.batchOperationMenu}>
      <Menu.Item key="batchTrain">
        <PermissionWrapper
          requiredPermissions={['Train']}
          instPermissions={permissions}>
          <Button
            type="text"
            className="w-full"
            icon={<TrademarkOutlined />}
            onClick={() => onTrain(selectedRowKeys)}
            disabled={!selectedRowKeys.length}
            loading={isTrainLoading}
          >
            {t('common.batchTrain')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="batchDelete">
        <PermissionWrapper
          requiredPermissions={['Delete']}
          instPermissions={permissions}>
          <Button
            type="text"
            className="w-full"
            icon={<DeleteOutlined />}
            onClick={() => onDelete(selectedRowKeys)}
            disabled={!selectedRowKeys.length}
          >
            {t('common.batchDelete')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="batchSet">
        <PermissionWrapper
          requiredPermissions={['Set']}
          instPermissions={permissions}>
          <Button
            type="text"
            className="w-full"
            icon={<TrademarkOutlined />}
            onClick={() => onBatchSet(selectedRowKeys)}
            disabled={!selectedRowKeys.length}
          >
            {t('knowledge.documents.batchSet')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  return (
    <Dropdown overlay={menu}>
      <Button>
        <Space>
          {t('common.batchOperation')}
          <DownOutlined />
        </Space>
      </Button>
    </Dropdown>
  );
};

export default BatchOperationMenu;
