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
import useApiNode from '@/app/node-manager/api';
import useApiCloudRegion from '@/app/node-manager/api/cloudRegion';
import type { TableDataItem } from '@/app/node-manager/types';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { COLLECTOR_LABEL } from '@/app/node-manager/constants/collector';
const { Option } = Select;

interface Option {
  value: string;
  label: string;
  children?: Option[];
}

const CollectorModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const { getCollectorlist } = useApiCollector();
    const { getPackageList } = useApiNode();
    const {
      installCollector,
      batchOperationCollector,
      getConfiglist,
      applyConfig,
    } = useApiCloudRegion();
    const cloudId = useCloudId();
    const collectorFormRef = useRef<FormInstance>(null);
    const popcConfirmArr = ['restartCollector', 'uninstallCollector'];
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
    const [options, setOptions] = useState<Option[]>([]);

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
      collectorFormRef.current?.resetFields();
    }, [collectorFormRef]);

    const configs = useMemo(() => {
      return configList.filter((item) => item.collector_id === collector);
    }, [collector]);

    const initPage = async (selectedsystem: string) => {
      setCollectorLoading(true);
      try {
        const data = await getCollectorlist({
          node_operating_system: selectedsystem,
        });
        const natsexecutorId =
          selectedsystem === 'linux'
            ? 'natsexecutor_linux'
            : 'natsexecutor_windows';
        const options: any = [];
        data?.forEach((item: any) => {
          if (item.id === natsexecutorId) {
            options.push({
              label: 'Controller',
              title: 'Controller',
              options: [
                {
                  label: item.name,
                  value: item.id,
                },
              ],
            });
            return;
          }
          const tag = getCollectorLabelKey(item.name);
          const tagIndex = options.findIndex((item: any) => item.title === tag);
          if (tagIndex >= 0) {
            options[tagIndex].options.push({
              label: item.name,
              value: item.id,
            });
          } else {
            options.push({
              label: tag,
              title: tag,
              options: [
                {
                  label: item.name,
                  value: item.id,
                },
              ],
            });
          }
        });
        setOptions(options);
        setCollectorlist(data);
      } finally {
        setCollectorLoading(false);
      }
    };

    const getConfigData = async () => {
      setConfigListLoading(true);
      try {
        const data = await getConfiglist({ cloud_region_id: cloudId });
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
      collectorFormRef.current?.validateFields().then((values) => {
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
            request = batchOperationCollector;
            startCollector(request, params);
            return;
          case 'restartCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'restart',
            };
            request = batchOperationCollector;
            break;
          case 'stopCollector':
            params = {
              node_ids: nodeIds,
              collector_id: collector,
              operation: 'stop',
            };
            request = batchOperationCollector;
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
      await applyConfig(params);
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

    const getCollectorLabelKey = (value: string = '') => {
      for (const key in COLLECTOR_LABEL) {
        if (COLLECTOR_LABEL[key].includes(value)) {
          return key;
        }
      }
    };

    const handleCollectorChange = async (option: string) => {
      console.log(option);
      const id = option;
      setCollector(id);
      setPackageList([]);
      collectorFormRef.current?.setFieldsValue({
        version: null,
        configuration: null,
      });
      const object = collectorlist.find(
        (item: TableDataItem) => item.id === id
      )?.name;
      if (type === 'installCollector' && id) {
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
            {popcConfirmArr.includes(type) ? (
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
        <Form ref={collectorFormRef} layout="vertical" colon={false}>
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
                showSearch
                allowClear
                loading={collectorLoading}
                options={options}
                onChange={handleCollectorChange}
              ></Select>
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
              <Select
                showSearch
                allowClear
                loading={configListLoading}
                placeholder={t('common.selectMsg')}
                filterOption={(input, option) =>
                  (option?.label || '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
                options={configs.map((item) => ({
                  value: item.id,
                  label: item.name,
                }))}
              />
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
              <Select
                showSearch
                allowClear
                loading={versionLoading}
                placeholder={t('common.selectMsg')}
                options={packageList.map((item) => ({
                  value: item.id,
                  label: item.version,
                }))}
                filterOption={(input, option) =>
                  (option?.label || '')
                    .toLowerCase()
                    .includes(input.toLowerCase())
                }
              />
            </Form.Item>
          )}
        </Form>
      </OperateModal>
    );
  }
);
CollectorModal.displayName = 'CollectorModal';
export default CollectorModal;
