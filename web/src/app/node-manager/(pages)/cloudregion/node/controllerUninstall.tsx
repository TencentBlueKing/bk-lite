'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useCallback,
  useMemo,
} from 'react';
import { Form, message, Button, Input, Popconfirm, InputNumber } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  ModalSuccess,
  ModalRef,
  TableDataItem,
} from '@/app/node-manager/types';
import useNodeManagerApi from '@/app/node-manager/api';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import { ControllerInstallFields } from '@/app/node-manager/types/cloudregion';
import CustomTable from '@/components/custom-table';
import BatchEditModal from './batchEditModal';
import { cloneDeep, isNumber } from 'lodash';

const ControllerUninstall = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess, config }, ref) => {
    const { t } = useTranslation();
    const cloudId = useCloudId();
    const { uninstallController } = useNodeManagerApi();
    //需要二次弹窗确定的类型
    const Popconfirmarr = ['uninstallSidecar'];
    const instRef = useRef<ModalRef>(null);
    const collectorformRef = useRef<FormInstance>(null);
    const [type, setType] = useState<string>('uninstallSidecar');
    const [collectorVisible, setCollectorVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [tableData, setTableData] = useState<TableDataItem[]>([]);

    const tableColumns = useMemo(
      () => [
        {
          title: t('node-manager.cloudregion.node.ipAdrress'),
          dataIndex: 'ip',
          width: 100,
          key: 'ip',
        },
        {
          title: (
            <>
              {t('node-manager.cloudregion.node.loginPort')}
              <EditOutlined
                className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
                onClick={() => batchEditModal('port')}
              />
            </>
          ),
          dataIndex: 'port',
          width: 100,
          key: 'port',
          render: (value: string, row: TableDataItem) => {
            return (
              <InputNumber
                className="w-full"
                min={1}
                precision={0}
                value={row.port}
                defaultValue={row.port}
                onChange={(e) => handlePortChange(e, row, 'port')}
              />
            );
          },
        },
        {
          title: (
            <>
              {t('node-manager.cloudregion.node.loginAccount')}
              <EditOutlined
                className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
                onClick={() => batchEditModal('username')}
              />
            </>
          ),
          dataIndex: 'username',
          width: 100,
          key: 'username',
          render: (value: string, row: TableDataItem) => {
            return (
              <Input
                defaultValue={row.username}
                value={row.username}
                placeholder={t('common.inputMsg')}
                onChange={(e) => handleInputBlur(e, row, 'username')}
              />
            );
          },
        },
        {
          title: (
            <>
              {t('node-manager.cloudregion.node.loginPassword')}
              <EditOutlined
                className="cursor-pointer ml-[10px] text-[var(--color-primary)]"
                onClick={() => batchEditModal('password')}
              />
            </>
          ),
          dataIndex: 'password',
          width: 100,
          key: 'password',
          render: (value: string, row: TableDataItem) => {
            return (
              <Input.Password
                defaultValue={row.usepasswordrname}
                value={row.password}
                placeholder={t('common.inputMsg')}
                onChange={(e) => handleInputBlur(e, row, 'password')}
              />
            );
          },
        },
      ],
      [tableData]
    );

    const handleBatchEdit = useCallback(
      (row: TableDataItem) => {
        const data = cloneDeep(tableData);
        data.forEach((item) => {
          item[row.field] = row.value;
        });
        setTableData(data);
      },
      [tableData]
    );

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form }) => {
        setCollectorVisible(true);
        setType(type);
        const list = (form?.list || []).map((item: TableDataItem) => ({
          id: item.id,
          os: item.operating_system,
          ip: item.ip,
          port: 22,
          username: null,
          password: null,
        }));
        setTableData(list);
      },
    }));

    useEffect(() => {
      collectorformRef.current?.resetFields();
    }, [collectorformRef]);

    const batchEditModal = (field: string) => {
      instRef.current?.showModal({
        title: t('common.bulkEdit'),
        type: field,
        form: {},
      });
    };

    const handleInputBlur = (
      e: React.ChangeEvent<HTMLInputElement>,
      row: TableDataItem,
      key: string
    ) => {
      const data = cloneDeep(tableData);
      const index = data.findIndex((item) => item.id === row.id);
      if (index !== -1) {
        data[index][key] = e.target.value;
        setTableData(data);
      }
    };

    const handlePortChange = (
      value: number,
      row: TableDataItem,
      key: string
    ) => {
      const data = cloneDeep(tableData);
      const index = data.findIndex((item) => item.id === row.id);
      if (index !== -1) {
        data[index][key] = value;
        setTableData(data);
      }
    };

    //关闭用户的弹窗(取消和确定事件)
    const handleCancel = () => {
      setCollectorVisible(false);
    };

    const validateTableData = async () => {
      const data = cloneDeep(tableData);
      if (!data.length) {
        return Promise.reject(new Error(t('common.required')));
      }
      if (
        tableData.every((item) =>
          Object.values(item).every((tex) =>
            isNumber(tex) ? !!tex : !!tex?.length
          )
        )
      ) {
        return Promise.resolve();
      }
      return Promise.reject(new Error(t('common.valueValidate')));
    };

    //点击确定按钮的相关逻辑处理
    const handleConfirm = () => {
      collectorformRef.current?.validateFields().then(() => {
        const data = cloneDeep(tableData);
        const params = {
          cloud_region_id: cloudId,
          work_node: config.work_node,
          nodes: data.map((item) => {
            delete item.id;
            return item;
          }),
        };
        uninstall(params);
      });
    };

    const uninstall = async (params = {}) => {
      setConfirmLoading(true);
      try {
        const data = await uninstallController(params);
        message.success(t('common.operationSuccessful'));
        handleCancel();
        onSuccess({
          taskId: data.task_id,
          type: 'uninstallController',
        });
      } finally {
        setConfirmLoading(false);
      }
    };

    return (
      <OperateModal
        title={t(`node-manager.cloudregion.node.${type}`)}
        open={collectorVisible}
        width={650}
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
                <Button type="primary" loading={confirmLoading}>
                  {t('common.confirm')}
                </Button>
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
          <Form.Item<ControllerInstallFields>
            name="nodes"
            label={t('node-manager.cloudregion.node.controllerInfo')}
            rules={[{ required: true, validator: validateTableData }]}
          >
            <CustomTable
              rowKey="id"
              columns={tableColumns}
              dataSource={tableData}
            />
          </Form.Item>
        </Form>
        <BatchEditModal
          ref={instRef}
          config={{
            systemList: OPERATE_SYSTEMS,
            groupList: [],
          }}
          onSuccess={handleBatchEdit}
        />
      </OperateModal>
    );
  }
);
ControllerUninstall.displayName = 'ControllerUninstall';
export default ControllerUninstall;
