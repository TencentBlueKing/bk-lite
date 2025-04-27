import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Tag, Tooltip, Button } from 'antd';
import type { TableColumnsType } from 'antd';
import { TableDataItem } from '@/app/node-manager/types/index';
import { useUserInfoContext } from '@/context/userInfo';
import Permission from '@/components/permission';

interface HookParams {
  checkConfig: (row: TableDataItem) => void;
}

export const useColumns = ({
  checkConfig,
}: HookParams): TableColumnsType<TableDataItem> => {
  const { t } = useTranslation();

  const columns = useMemo(
    (): TableColumnsType<TableDataItem> => [
      {
        title: t('node-manager.cloudregion.node.ip'),
        dataIndex: 'ip',
        key: 'ip',
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        key: 'name',
      },
      {
        title: 'Sidecar',
        dataIndex: 'sidecar',
        render: (key: string, item) => {
          return (
            <Tooltip title={`${item.status?.message}`}>
              <Tag
                bordered={false}
                color={!item.status?.status ? 'success' : 'error'}
              >
                {!item.status?.status ? 'Running' : 'Error'}
              </Tag>
            </Tooltip>
          );
        },
      },
      {
        key: 'action',
        title: t('common.actions'),
        dataIndex: 'action',
        fixed: 'right',
        width: 140,
        render: (key, item) => (
          <Permission requiredPermissions={["View"]}>
            <Button type="link" onClick={() => checkConfig(item)}>
              {t('node-manager.cloudregion.node.checkConfig')}
            </Button>
          </Permission>
        ),
      },
    ],
    [checkConfig, t]
  );
  return columns;
};

export const useGroupNames = () => {
  const commonContext = useUserInfoContext();
  const showGroupNames = (ids: string[]) => {
    const groups = commonContext?.groups || [];
    const groupName = ids.map(
      (item) => groups.find((group) => group.id === item)?.name
    );
    return groupName.join(',');
  };
  return {
    showGroupNames,
  };
};
