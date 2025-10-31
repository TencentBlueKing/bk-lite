import React from 'react';
import { Input, Select, Button, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TableDataItem } from '@/app/log/types';
import { IntegrationLogInstance } from '@/app/log/types/integration';
import GroupTreeSelector from '@/components/group-tree-select';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';
const useCommonColumns = () => {
  const { t } = useTranslation();

  return {
    getCommonColumns: (config: {
      nodeList: TableDataItem[];
      dataSource: TableDataItem[];
      initTableItems: IntegrationLogInstance;
      onTableDataChange: (data: TableDataItem[]) => void;
    }) => {
      const getFilterNodes = (id: string) => {
        const nodeIds = config.dataSource
          .map((item) => item.node_ids)
          .filter((item) => item !== id);
        const _nodeList = config.nodeList.filter(
          (item) => !nodeIds.includes(item.id as string)
        );
        return _nodeList;
      };

      const handleFilterNodeChange = (val: string, index: number) => {
        const _dataSource = cloneDeep(config.dataSource);
        _dataSource[index].node_ids = val;
        config.onTableDataChange(_dataSource);
      };

      const handleInputChange = (
        e: React.ChangeEvent<HTMLInputElement>,
        extra: {
          index: number;
          field: string;
        }
      ) => {
        const _dataSource = cloneDeep(config.dataSource);
        _dataSource[extra.index][extra.field] = e.target.value;
        config.onTableDataChange(_dataSource);
      };

      const handleGroupChange = (val: number[], index: number) => {
        const _dataSource = cloneDeep(config.dataSource);
        _dataSource[index].group_ids = val;
        config.onTableDataChange(_dataSource);
      };

      const handleAdd = (id: string) => {
        const index = config.dataSource.findIndex(
          (item) => item.instance_id === id
        );
        const newData = {
          ...config.initTableItems,
          instance_id: replaceDynamicUUID(
            config.initTableItems?.instance_id || ''
          ),
        };
        const updatedData = [...config.dataSource];
        updatedData.splice(index + 1, 0, newData); // 在当前行下方插入新数据
        config.onTableDataChange(updatedData);
      };

      const handleCopy = (row: IntegrationLogInstance) => {
        const index = config.dataSource.findIndex(
          (item) => item.instance_id === row.instance_id
        );
        const newData: IntegrationLogInstance = {
          ...row,
          instance_id: replaceDynamicUUID(
            config.initTableItems?.instance_id || ''
          ),
        };
        const updatedData = [...config.dataSource];
        updatedData.splice(index + 1, 0, newData);
        config.onTableDataChange(updatedData);
      };

      const handleDelete = (id: string) => {
        const updatedData = config.dataSource.filter(
          (item) => item.instance_id !== id
        );
        config.onTableDataChange(updatedData);
      };

      const replaceDynamicUUID = (
        originalStr: string,
        prefixPattern = '.*'
      ) => {
        // UUID格式（8-4-4-4-12）
        const uuidRegex =
          /[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/i;
        // 构建完整正则：前缀 + UUID
        const dynamicRegex = new RegExp(
          `(${prefixPattern}-)${uuidRegex.source}`
        );
        if (!dynamicRegex.test(originalStr)) {
          return uuidv4();
        }
        return originalStr.replace(dynamicRegex, `$1${uuidv4()}`);
      };

      return [
        {
          title: t('log.integration.node'),
          dataIndex: 'node_ids',
          key: 'node_ids',
          width: 200,
          render: (_: unknown, record: TableDataItem, index: number) => (
            <Select
              showSearch
              value={record.node_ids}
              onChange={(val) => handleFilterNodeChange(val, index)}
              filterOption={(input, option) =>
                (option?.label || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              options={getFilterNodes(record.node_ids).map((item) => ({
                value: item.id,
                label: `${item.name}（${item.ip}）`,
              }))}
            ></Select>
          ),
        },
        {
          title: t('log.integration.instanceName'),
          dataIndex: 'instance_name',
          key: 'instance_name',
          width: 200,
          render: (_: unknown, record: TableDataItem, index: number) => (
            <Input
              value={record.instance_name}
              onChange={(e) =>
                handleInputChange(e, {
                  index,
                  field: 'instance_name',
                })
              }
            />
          ),
        },
        {
          title: (
            <Tooltip title={t('log.integration.belongingGroupTips')}>
              {
                <span
                  className="pb-[2px]"
                  style={{ borderBottom: '1px dashed var(--color-border-4)' }}
                >
                  {t('common.belongingGroup')}
                </span>
              }
            </Tooltip>
          ),
          dataIndex: 'group_ids',
          key: 'group_ids',
          width: 200,
          render: (_: unknown, record: TableDataItem, index: number) => (
            <GroupTreeSelector
              value={record.group_ids}
              onChange={(val) => handleGroupChange(val as number[], index)}
            />
          ),
        },
        {
          title: t('common.action'),
          key: 'action',
          dataIndex: 'action',
          width: 160,
          fixed: 'right',
          render: (_: unknown, record: TableDataItem, index: number) => (
            <>
              <Button
                type="link"
                className="mr-[10px]"
                onClick={() => handleAdd(record.instance_id)}
              >
                {t('common.add')}
              </Button>
              <Button
                type="link"
                className="mr-[10px]"
                onClick={() => handleCopy(record as IntegrationLogInstance)}
              >
                {t('common.copy')}
              </Button>
              {!!index && (
                <Button
                  type="link"
                  onClick={() => handleDelete(record.instance_id)}
                >
                  {t('common.delete')}
                </Button>
              )}
            </>
          ),
        },
      ];
    },
  };
};
export { useCommonColumns };
