import React from 'react';
import { Input, Select, Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TableDataItem } from '@/app/monitor/types';
import { IntegrationMonitoredObject } from '@/app/monitor/types/integration';
import GroupTreeSelector from '@/components/group-tree-select';
import { cloneDeep } from 'lodash';
import { v4 as uuidv4 } from 'uuid';
const useCommonColumns = () => {
  const { t } = useTranslation();

  return {
    getCommonColumns: (config: {
      nodesLoading: boolean;
      nodeList: TableDataItem[];
      dataSource: TableDataItem[];
      collectType: string;
      initTableItems: IntegrationMonitoredObject;
      onTableDataChange: (data: TableDataItem[]) => void;
    }) => {
      const getFilterNodes = (id: string) => {
        if (['ipmi', 'snmp'].includes(config.collectType)) {
          return config.nodeList;
        }
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
        if (['host', 'trap'].includes(config.collectType)) {
          _dataSource[index].instance_name =
            config.nodeList.find((item) => item.id === val)?.name || '';
        }
        config.onTableDataChange(_dataSource);
      };

      const handleNodeChange = (val: string[], index: number) => {
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

      const handleAdd = (key: string) => {
        const index = config.dataSource.findIndex((item) => item.key === key);
        const newData = {
          ...config.initTableItems,
          key: uuidv4(),
        };
        const updatedData = [...config.dataSource];
        updatedData.splice(index + 1, 0, newData); // 在当前行下方插入新数据
        config.onTableDataChange(updatedData);
      };

      const handleCopy = (row: IntegrationMonitoredObject) => {
        const index = config.dataSource.findIndex(
          (item) => item.key === row.key
        );
        const newData: IntegrationMonitoredObject = { ...row, key: uuidv4() };
        const updatedData = [...config.dataSource];
        updatedData.splice(index + 1, 0, newData);
        config.onTableDataChange(updatedData);
      };

      const handleDelete = (key: string) => {
        const updatedData = config.dataSource.filter(
          (item) => item.key !== key
        );
        config.onTableDataChange(updatedData);
      };

      const columns = [
        {
          title: t('monitor.integrations.node'),
          dataIndex: 'node_ids',
          key: 'node_ids',
          width: 200,
          render: (_: unknown, record: TableDataItem, index: number) => (
            <Select
              showSearch
              loading={config.nodesLoading}
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
          title: t('monitor.integrations.node'),
          dataIndex: 'node_ids',
          key: 'node_ids',
          width: 200,
          render: (_: unknown, record: TableDataItem, index: number) => (
            <Select
              showSearch
              mode="tags"
              maxTagCount="responsive"
              loading={config.nodesLoading}
              value={record.node_ids}
              onChange={(val) => handleNodeChange(val, index)}
              filterOption={(input, option) =>
                (option?.label || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              options={config.nodeList.map((item) => ({
                value: item.id,
                label: `${item.name}（${item.ip}）`,
              }))}
            ></Select>
          ),
        },
        {
          title: t('monitor.integrations.instanceName'),
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
          title: t('common.group'),
          dataIndex: 'group_ids',
          key: 'group_ids',
          width: 200,
          render: (_: unknown, record: TableDataItem, index: number) => (
            <GroupTreeSelector
              value={record.group_ids}
              onChange={(val) => handleGroupChange(val, index)}
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
                onClick={() => handleAdd(record.key)}
              >
                {t('common.add')}
              </Button>
              {!['host', 'trap'].includes(config.collectType) && (
                <Button
                  type="link"
                  className="mr-[10px]"
                  onClick={() =>
                    handleCopy(record as IntegrationMonitoredObject)
                  }
                >
                  {t('common.copy')}
                </Button>
              )}
              {!!index && (
                <Button type="link" onClick={() => handleDelete(record.key)}>
                  {t('common.delete')}
                </Button>
              )}
            </>
          ),
        },
      ];

      return ['web', 'ping'].includes(config.collectType)
        ? columns.slice(1, 5)
        : [columns[0], ...columns.slice(2, 5)];
    },
  };
};
export { useCommonColumns };
