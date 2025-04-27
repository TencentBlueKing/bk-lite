'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useMemo,
  useEffect,
} from 'react';
import { Form, Select, message, Button, Popconfirm } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ModalSuccess, ModalRef } from '@/app/node-manager/types';
import useApiCollector from '@/app/node-manager/api/collector';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import type { TableDataItem } from '@/app/node-manager/types';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
const { Option } = Select;

const CollectorModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { getCollectorlist, getPackageList } = useApiCollector();
    const {
      installCollector,
      batchoperationcollector,
      getconfiglist,
      applyconfig,
    } = useApiCloudRegion();
    const cloudId = useCloudId();
    const collectorformRef = useRef<FormInstance>(null);
    const Popconfirmarr = ['restartCollector', 'uninstallCollector'];
    const [type, setType] = useState<string>('installCollector');
    const [nodeIds, setNodeIds] = useState<string[]>(['']);
    const [collectorVisible, setCollectorVisible] = useState<boolean>(false);
    const [packageList, setPackageList] = useState<TableDataItem[]>([]);
    const [collectorlist, setCollectorlist] = useState<TableDataItem[]>([]);
    const [configList, setConfigList] = useState<TableDataItem[]>([]);
    const [versionLoading, setVersionLoading] = useState<boolean>(false);
    const [collectorLoading, setCollectorLoading] = useState<boolean>(false);
    const [configListLoading, setConfigListLoading] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [collector, setCollector] = useState<string | null>(null);
    const [system, setSystem] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ type, ids, selectedsystem }) => {
        setCollectorVisible(true);
        setType(type);
        setSystem(selectedsystem as string);
        setNodeIds(ids || []);
        initPage(selectedsystem || '');
        type === 'startCollector' && getConfigData();
      },
    }));

    useEffect(() => {
      collectorformRef.current?.resetFields();
    }, [collectorformRef]);

    const configs = useMemo(() => {
      return configList.filter((item) => item.collector_id === collector);
    }, [collector]);

    const initPage = async (selectedsystem: string) => {
      setCollectorLoading(true);
      try {
        const data = await getCollectorlist({
          node_operating_system: selectedsystem,
        });
        setCollectorlist(data);
      } finally {
        setCollectorLoading(false);
      }
    };

    const getConfigData = async () => {
      setConfigListLoading(true);
      try {
        const data = await getconfiglist({ cloud_region_id: cloudId });
        setConfigList(data);
      } finally {
        setConfigListLoading(false);
      }
    };

    //关闭用户的弹窗(取消和确定事件)
    const handleCancel = () => {
      setCollectorVisible(false);
      setVersionLoading(false);
      setCollectorLoading(false);
      setCollector(null);
    };

    //点击确定按钮的相关逻辑处理
    const handleConfirm = () => {
      //表单验证
      collectorformRef.current?.validateFields().then((values) => {
        let request: any = installCollector;
        let params: any = {
          nodes: nodeIds,
          collector_package: values.version,
        };
        switch (type) {
          case 'startCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              configuration: values.configuration,
              operation: 'start',
            };
            request = batchoperationcollector;
            startCollector(request, params);
            return;
          case 'restartCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'restart',
            };
            request = batchoperationcollector;
            break;
          case 'stopCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'stop',
            };
            request = batchoperationcollector;
            break;
          default:
            break;
        }
        operate(request, params);
      });
    };

    const startCollector = (callback: any, params: any) => {
      const { configuration, ...rest } = params;
      Promise.all([
        operate(callback, rest, !!configuration),
        configuration && handleApply(configuration),
      ])
        .then(() => {
          if (configuration) {
            message.success(t('common.operationSuccessful'));
            handleCancel();
          }
        })
        .finally(() => {
          setConfirmLoading(false);
        });
    };

    const handleApply = async (id: string) => {
      const params = nodeIds.map((item) => ({
        node_id: item,
        collector_configuration_id: id,
      }));
      await applyconfig(params);
    };

    const operate = async (
      callback: any,
      params: any,
      keepLoading?: boolean
    ) => {
      try {
        setConfirmLoading(true);
        const data = await callback(params);
        const config = {
          taskId: data.task_id || '',
          type,
        };
        if (!keepLoading) {
          message.success(t('common.operationSuccessful'));
          handleCancel();
        }
        onSuccess(config);
      } finally {
        setConfirmLoading(!!keepLoading);
      }
    };

    const handleCollectorChange = async (value: string) => {
      setCollector(value);
      setPackageList([]);
      collectorformRef.current?.setFieldsValue({
        version: null,
        configuration: null,
      });
      const object = collectorlist.find(
        (item: TableDataItem) => item.id === value
      )?.name;
      if (type === 'installCollector' && value) {
        try {
          setVersionLoading(true);
          const data = await getPackageList({ object, os: system });
          setPackageList(data);
        } finally {
          setVersionLoading(false);
        }
      }
    };

    return (
      <OperateModal
        title={t(`node-manager.cloudregion.node.${type}`)}
        open={collectorVisible}
        destroyOnClose
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={handleCancel}
        footer={
          <>
            <Button key="back" onClick={handleCancel}>
              {t('common.cancel')}
            </Button>
            {Popconfirmarr.includes(type) ? (
              <Popconfirm
                title={t(`node-manager.cloudregion.node.${type}`)}
                description={t(`node-manager.cloudregion.node.${type}Info`)}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                onConfirm={handleConfirm}
              >
                <Button type="primary">{t('common.confirm')}</Button>
              </Popconfirm>
            ) : (
              <Button
                type="primary"
                loading={confirmLoading}
                onClick={handleConfirm}
              >
                {t('common.confirm')}
              </Button>
            )}
          </>
        }
      >
        <Form ref={collectorformRef} layout="vertical" colon={false}>
          <Form.Item noStyle>
            <Form.Item
              name="Collector"
              label={t('node-manager.cloudregion.node.collector')}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Select
                value={collector}
                loading={collectorLoading}
                showSearch
                allowClear
                onChange={handleCollectorChange}
              >
                {collectorlist.map((item) => (
                  <Option value={item.id} key={item.id}>
                    {item.name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
            {type === 'startCollector' && collector?.includes('telegraf') && (
              <div className="text-[12px] text-[var(--color-text-2)]">
                {t('node-manager.cloudregion.node.telegrafConfigTips')}
              </div>
            )}
          </Form.Item>
          {type === 'startCollector' &&
            collector &&
            !collector.includes('telegraf') && (
            <Form.Item
              name="configuration"
              label={t('node-manager.cloudregion.node.configuration')}
            >
              <Select showSearch allowClear loading={configListLoading}>
                {configs.map((item) => (
                  <Option value={item.id} key={item.id}>
                    {item.name}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}
          {type === 'installCollector' && (
            <Form.Item
              name="version"
              label={t('node-manager.cloudregion.node.version')}
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Select showSearch allowClear loading={versionLoading}>
                {packageList.map((item) => (
                  <Option value={item.id} key={item.id}>
                    {item.version}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          )}
        </Form>
      </OperateModal>
    );
  }
);
CollectorModal.displayName = 'CollectorModal';
export default CollectorModal;
