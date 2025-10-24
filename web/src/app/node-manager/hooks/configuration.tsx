import { useMemo } from 'react';
import { useTranslation } from '@/utils/i18n';
import { Button, Tag, Popconfirm } from 'antd';
import type { TableColumnsType } from 'antd';
import PermissionWrapper from '@/components/permission';
import {
  ConfigHookParams,
  SubConfigHookParams,
} from '@/app/node-manager/types/cloudregion';
import { TableDataItem } from '@/app/node-manager/types/index';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import type { MenuProps } from 'antd';

const useConfigBtachItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['Delete']}
          >
            {t('common.delete')}
          </PermissionWrapper>
        ),
        key: 'delete',
      },
    ],
    [t]
  );
};

const useApplyColumns = ({
  handleApply,
}: {
  handleApply: (row: TableDataItem) => void;
}): TableColumnsType => {
  const { t } = useTranslation();
  //数据
  const applycolumns: TableColumnsType = [
    {
      title: t('node-manager.cloudregion.Configuration.ip'),
      dataIndex: 'ip',
    },
    {
      title: t('node-manager.cloudregion.Configuration.system'),
      dataIndex: 'operatingSystem',
    },
    {
      title: t('node-manager.cloudregion.Configuration.sidecar'),
      dataIndex: 'sidecar',
      className: 'table-cell-center',
      render: (key: string) => {
        if (key === 'Running') {
          return (
            <Tag bordered={false} color="success">
              {key}
            </Tag>
          );
        }
        return (
          <Tag bordered={false} color="error">
            {key}
          </Tag>
        );
      },
    },
    {
      title: t('common.actions'),
      dataIndex: 'key',
      fixed: 'right',
      render: (key: string, sidecarinfo) => {
        return (
          <div>
            {sidecarinfo.isRelated ? (
              <Button
                type="link"
                onClick={() => {
                  handleApply(sidecarinfo);
                }}
              >
                {t('common.unapply')}
              </Button>
            ) : (
              <Button
                disabled={sidecarinfo.sidecar != 'Running'}
                type="link"
                onClick={() => {
                  handleApply(sidecarinfo);
                }}
              >
                {t('common.apply')}
              </Button>
            )}
          </div>
        );
      },
    },
  ];
  return applycolumns;
};

const useConfigColumns = ({
  configurationClick,
  openSub,
  nodeClick,
  modifyDeleteconfirm,
  applyConfigurationClick,
  filter,
}: ConfigHookParams) => {
  const { t } = useTranslation();
  const columns: TableColumnsType<TableDataItem> = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      width: 150,
    },
    {
      title: t('node-manager.cloudregion.node.node'),
      dataIndex: 'nodes',
      width: 150,
      render: (_, record) => {
        return (
          <>
            {record.nodes?.length ? (
              <Button
                type="link"
                className="text-blue-500 hover:text-blue-700"
                onClick={() => nodeClick()}
              >
                <EllipsisWithTooltip
                  text={(record.nodes || [])
                    .map((item: TableDataItem) => item.ip)
                    .join(',')}
                  className="w-[150px] overflow-hidden text-ellipsis whitespace-nowrap text-left"
                />
              </Button>
            ) : (
              '--'
            )}
          </>
        );
      },
    },
    {
      title: t('node-manager.cloudregion.node.system'),
      dataIndex: 'operatingSystem',
      width: 150,
      render: (_, record) =>
        t(`node-manager.cloudregion.Configuration.${record.operatingSystem}`),
    },
    {
      title: t('node-manager.cloudregion.Configuration.sidecar'),
      dataIndex: 'collector_name',
      align: 'center',
      filters: filter,
      width: 150,
      onFilter: (value, record) => {
        return record?.collector_name === value;
      },
    },
    {
      title: t('common.actions'),
      dataIndex: 'key',
      fixed: 'right',
      align: 'center',
      width: 240,
      render: (key, item) => (
        <div className="flex justify-center">
          <PermissionWrapper requiredPermissions={['Apply']}>
            <Button
              color="primary"
              variant="link"
              onClick={() => {
                applyConfigurationClick(item);
              }}
            >
              {t('common.apply')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              color="primary"
              variant="link"
              onClick={() => {
                configurationClick(key);
              }}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['SubConfiguration']}>
            <Button
              color="primary"
              variant="link"
              onClick={() => {
                openSub(key, item);
              }}
            >
              {t('node-manager.cloudregion.Configuration.subconfiguration')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('common.prompt')}
              description={t(
                'node-manager.cloudregion.Configuration.modifydelinfo'
              )}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => modifyDeleteconfirm(item.key)}
            >
              <Button
                variant="link"
                color="primary"
                disabled={!!item.nodes?.length}
              >
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </div>
      ),
    },
  ];

  return {
    columns,
  };
};

const useSubConfigColumns = ({ nodeData, edit }: SubConfigHookParams) => {
  const { t } = useTranslation();
  const columns: TableColumnsType<TableDataItem> = [
    {
      title: t('node-manager.cloudregion.Configuration.collectionType'),
      dataIndex: 'collect_type',
    },
    {
      title: t('node-manager.cloudregion.Configuration.configurationType'),
      dataIndex: 'config_type',
    },
    {
      title: t('common.actions'),
      dataIndex: 'key',
      fixed: 'right',
      align: 'center',
      width: 180,
      render: (_: any, record: any) => (
        <div className="flex justify-center">
          <Button
            color="primary"
            variant="link"
            onClick={() => {
              edit({
                ...record,
                nodes: nodeData.nodes || [],
                collector: nodeData.collector,
                nodesList: nodeData.nodesList,
                configInfo: record.content,
                operating_system: nodeData.operating_system,
              });
            }}
          >
            {t('common.edit')}
          </Button>
        </div>
      ),
    },
  ];

  return {
    columns,
  };
};

const useConfigModalColumns = () => {
  const { t } = useTranslation();
  return [
    {
      title: t('node-manager.cloudregion.Configuration.variable'),
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: t('node-manager.cloudregion.Configuration.description'),
      dataIndex: 'description',
      key: 'description',
    },
  ];
};

export {
  useConfigBtachItems,
  useApplyColumns,
  useConfigColumns,
  useSubConfigColumns,
  useConfigModalColumns,
};
