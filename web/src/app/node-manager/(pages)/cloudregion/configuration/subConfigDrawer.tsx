'use client';

import React, {
  useState,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useRef,
} from 'react';
import { Button, Tag } from 'antd';
import OperateDrawer from '@/app/log/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { ModalRef, TableDataItem } from '@/app/node-manager/types';
import { ConfigData } from '@/app/node-manager/types/cloudregion';
import { Pagination } from '@/app/node-manager/types';
import CustomTable from '@/components/custom-table';
import Permission from '@/components/permission';
import useNodeManagerApi from '@/app/node-manager/api';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import ConfigModal from './configModal';

interface SubConfigDrawerProps {
  collectors?: TableDataItem[];
  onSuccess?: () => void;
}

const SubConfigDrawer = forwardRef<ModalRef, SubConfigDrawerProps>(
  ({ collectors = [], onSuccess }, ref) => {
    const { t } = useTranslation();
    const { getChildConfig } = useNodeManagerApi();
    const { isLoading } = useApiClient();
    const configModalRef = useRef<ModalRef>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [tableLoading, setTableLoading] = useState<boolean>(false);
    const [tableData, setTableData] = useState<any[]>([]);
    const [pagination, setPagination] = useState<Pagination>({
      current: 1,
      total: 0,
      pageSize: 20,
    });
    const [nodeData, setNodeData] = useState<ConfigData>({
      key: '',
      name: '',
      collector_id: '',
      operatingSystem: '',
      nodeCount: 0,
      configInfo: '',
      nodes: [],
    });

    const columns = [
      {
        title: t('node-manager.cloudregion.Configuration.collectionType'),
        dataIndex: 'collect_type',
        key: 'collect_type',
        width: 150,
        render: (text: string) => <Tag color="green">{text}</Tag>,
      },
      {
        title: t('node-manager.cloudregion.Configuration.configurationType'),
        dataIndex: 'config_type',
        key: 'config_type',
        width: 150,
      },
      {
        title: t('common.action'),
        key: 'action',
        dataIndex: 'action',
        width: 100,
        fixed: 'right' as const,
        render: (_: any, record: any) => (
          <div className="flex gap-2">
            <Permission requiredPermissions={['Edit']}>
              <Button type="link" onClick={() => handleEdit(record)}>
                {t('common.edit')}
              </Button>
            </Permission>
          </div>
        ),
      },
    ];

    useEffect(() => {
      if (!isLoading && visible && nodeData.key) {
        getChildConfigList();
      }
    }, [pagination.current, pagination.pageSize]);

    useImperativeHandle(ref, () => ({
      showModal: ({ form }) => {
        setVisible(true);
        const row: any = form;
        if (row) {
          setNodeData(row);
          getChildConfigList(row);
        }
      },
    }));

    const handleEdit = (record: any) => {
      showConfigModal('edit_child', record);
    };

    const showConfigModal = (type: string, form: any) => {
      configModalRef.current?.showModal({
        type,
        form,
      });
    };

    const getChildConfigList = async (nodeForm = nodeData) => {
      setTableLoading(true);
      try {
        const params = {
          collector_config_id: nodeForm.key,
          search: '',
          page: pagination.current,
          page_size: pagination.pageSize,
        };
        const res = await getChildConfig(params);
        const data = res.items.map((item: any) => {
          return {
            key: item.id,
            name: `${nodeForm.nodes || '--'}_${nodeForm.name}_子配置`,
            ...item,
          };
        });
        setTableData(data);
        setPagination((prev: Pagination) => ({
          ...prev,
          total: res?.count || 0,
        }));
      } catch (error) {
        console.error('Failed to get child config:', error);
      } finally {
        setTableLoading(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
      setTableData([]);
      setPagination({
        current: 1,
        total: 0,
        pageSize: 20,
      });
      setNodeData({
        key: '',
        name: '',
        collector_id: '',
        operatingSystem: '',
        nodeCount: 0,
        configInfo: '',
        nodes: [],
      });
    };

    const handleTableChange = (pagination: any) => {
      setPagination(pagination);
    };

    const handleMainConfigEdit = () => {
      showConfigModal('edit', nodeData);
    };

    const handleConfigModalSuccess = (operateType: string) => {
      if (['add_child', 'edit_child'].includes(operateType)) {
        getChildConfigList();
        return;
      }
      onSuccess?.();
    };

    return (
      <div>
        <OperateDrawer
          title={t(
            'node-manager.cloudregion.Configuration.configurationDetails'
          )}
          subTitle={nodeData.name}
          open={visible}
          width={600}
          destroyOnClose
          onClose={handleCancel}
          footer={
            <div className="flex justify-end">
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <div className="mb-[10px]">
            <h3 className="text-lg font-medium mb-[10px]">
              {collectors.find((item) => item.id === nodeData.collector_id)
                ?.name || nodeData.collector_id}
            </h3>
            <ul>
              <li className="flex items-center justify-between mb-[10px]">
                <b>
                  {t(
                    'node-manager.cloudregion.Configuration.mainConfiguration'
                  )}
                </b>
                <Permission requiredPermissions={['Edit']}>
                  <Button type="primary" onClick={handleMainConfigEdit}>
                    {t('common.edit')}
                  </Button>
                </Permission>
              </li>
              <li className="flex items-center justify-between mb-[10px]">
                <span className="text-[var(--color-text-2)]">
                  {t('node-manager.cloudregion.node.system')}
                </span>
                <span>
                  {OPERATE_SYSTEMS.find(
                    (item) => item.value === nodeData.operating_system
                  )?.label || '--'}
                </span>
              </li>
              <li className="flex items-center justify-between mb-[10px]">
                <span className="text-[var(--color-text-2)]">
                  {t('node-manager.cloudregion.Configuration.collectorType')}
                </span>
                <span>
                  {collectors.find((item) => item.id === nodeData.collector_id)
                    ?.name || nodeData.collector_id}
                </span>
              </li>
            </ul>
          </div>
          <div>
            <div
              className="flex justify-between items-center mb-[10px]  pt-[10px] border-t"
              style={{ borderTop: '1px solid var(--color-border-1)' }}
            >
              <b>
                {t('node-manager.cloudregion.Configuration.subconfiguration')}
              </b>
            </div>
            <CustomTable
              scroll={{ y: 'calc(100vh - 450px)', x: 'max-content' }}
              columns={columns}
              dataSource={tableData}
              loading={tableLoading}
              rowKey="id"
              pagination={pagination}
              onChange={handleTableChange}
            />
          </div>
        </OperateDrawer>
        <ConfigModal
          ref={configModalRef}
          config={{ collectors }}
          onSuccess={handleConfigModalSuccess}
        />
      </div>
    );
  }
);

SubConfigDrawer.displayName = 'SubConfigDrawer';
export default SubConfigDrawer;
