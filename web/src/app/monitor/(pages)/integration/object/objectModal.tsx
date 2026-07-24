'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect
} from 'react';
import {
  Input,
  InputNumber,
  Radio,
  Button,
  Form,
  message,
  Popover,
  Spin
} from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { ModalRef } from '@/app/monitor/types';
import { ObjectFormData, ChildObject, MonitorObjectItem } from './types';
import { useTranslation } from '@/utils/i18n';
import useObjectApi from './api';

// 默认图标
const DEFAULT_ICON = 'cc-default_默认';

// 可用的图标列表
const ICON_LIST = [
  'cc-host_主机',
  'cc-mysql_MySQL',
  'cc-redis_REDIS',
  'cc-nginx_Nginx',
  'cc-docker_Docker',
  'cc-k8s-cluster_K8S集群',
  'cc-mongodb_MongoDB',
  'cc-postgresql_PostgreSQL',
  'cc-oracle_Oracle',
  'cc-elasticsearch_ElasticSearch',
  'cc-kafka_Kafka',
  'cc-rabbitmq_RabbitMQ',
  'cc-tomcat_Tomcat',
  'cc-apache_Apache',
  'cc-middleware_中间件',
  'cc-cloud_云',
  'cc-cloud-host_云主机',
  'cc-db_数据库',
  'cc-storage_存储',
  'cc-firewall_防火墙',
  'cc-router_路由器',
  'cc-switch2_交换机',
  'cc-equipment_设备',
  'cc-default_默认',
  'cc-business_业务',
  'cc-module_模块',
  'cc-set_集群',
  'cc-application_子应用',
  'cc-node_Node',
  'cc-pod_Pod',
  'cc-zookeeper_ZooKeeper',
  'cc-nacos_Nacos',
  'cc-minio_Minio',
  'cc-tidb_TiDB',
  'cc-dameng_达梦',
  'cc-db2_DB2',
  'cc-sql-server_MSSQL',
  'cc-weblogic_WebLogic',
  'cc-websphere_websphere',
  'cc-iis_IIS',
  'mm-activemq_ActiveMQ',
  'mm-apache_Apache',
  'mm-cvm_云服务器',
  'mm-datastorage_数据存储',
  'mm-db2_DB2',
  'mm-docker_Docker',
  'mm-elasticsearch_Elasticsearch',
  'mm-esxi_ESXI',
  'mm-firewall_防火墙',
  'mm-hardwareDevice_硬件设备',
  'mm-host_主机',
  'mm-jetty_Jetty',
  'mm-jvm_JVM',
  'mm-k8s_K8S',
  'mm-kafka_Kafka',
  'mm-loadbalance_负载均衡',
  'mm-middleware_中间件',
  'mm-minio_Minio',
  'mm-mongodb_Mongodb',
  'mm-mssql_Mssql',
  'mm-mysql_Mysql',
  'mm-nginx_Nginx',
  'mm-node_Node',
  'mm-oracle_Oracle',
  'mm-pod_Pod',
  'mm-postgresql_Postgresql',
  'mm-rabbitmq_Rabbitmq',
  'mm-redis_Redis',
  'mm-router_路由器',
  'mm-storage_储存设备',
  'mm-switch_交换机',
  'mm-tencentCloud_腾讯云',
  'mm-tomcat_Tomcat',
  'mm-vm_虚拟机',
  'mm-vmware_Vmware',
  'mm-weblogic_Weblogic',
  'mm-website_网站',
  'mm-zookeeper_Zookeeper'
];

interface ModalProps {
  onSuccess: () => void;
  typeId?: string;
}

const ObjectModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, typeId }, ref) => {
    const { t } = useTranslation();
    const { createObject, updateObject, getObjectChildren } = useObjectApi();
    const formRef = useRef<FormInstance>(null);
    const [visible, setVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [dataLoading, setDataLoading] = useState<boolean>(false);
    const [formData, setFormData] = useState<ObjectFormData>(
      {} as ObjectFormData
    );
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');
    const [selectedIcon, setSelectedIcon] = useState<string>(DEFAULT_ICON);
    const [children, setChildren] = useState<ChildObject[]>([]);
    const [iconPopoverOpen, setIconPopoverOpen] = useState(false);

    useImperativeHandle(ref, () => ({
      showModal: async ({ type, form, title }) => {
        setVisible(true);
        setType(type);
        setTitle(title);
        const data = form as ObjectFormData & { children_count?: number };
        setFormData(data);
        // 设置图标：有值用值，没有用默认
        setSelectedIcon(data.icon || DEFAULT_ICON);
        setChildren(data.children || []);

        // 编辑模式下，如果有子对象数量，则加载子对象
        if (
          type === 'edit' &&
          data.id &&
          !data.is_builtin &&
          (data as MonitorObjectItem).children_count &&
          (data as MonitorObjectItem).children_count! > 0
        ) {
          setDataLoading(true);
          try {
            const childrenData = await getObjectChildren(data.id);
            setChildren(childrenData);
          } catch {
            // 加载失败不影响编辑
          } finally {
            setDataLoading(false);
          }
        }
      }
    }));

    useEffect(() => {
      if (visible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue({
          ...formData,
          display_name: formData.display_name || formData.name,
          cleanup_policy: formData.cleanup_policy || 'no_cleanup',
          cleanup_timeout_days: formData.cleanup_timeout_days || 1
        });
      }
    }, [visible, formData]);

    const handleSubmit = () => {
      const isBuiltin = type === 'edit' && formData.is_builtin;
      // 验证图标必填
      if (!isBuiltin && !selectedIcon) {
        message.error(t('monitor.object.iconRequired'));
        return;
      }

      formRef.current?.validateFields().then(async (values) => {
        try {
          setConfirmLoading(true);
          const submitData = (isBuiltin
            ? {
              cleanup_policy: values.cleanup_policy,
              cleanup_timeout_days: values.cleanup_timeout_days
            }
            : {
              ...values,
              icon: selectedIcon,
              type_id: typeId || formData.type_id,
              children: children.filter((c) => c.id && c.name)
            }) as ObjectFormData;

          if (type === 'add') {
            await createObject(submitData);
            message.success(t('common.addSuccess'));
          } else {
            await updateObject(formData.id!, submitData);
            message.success(t('common.updateSuccess'));
          }
          handleCancel();
          onSuccess();
        } catch {
          message.error(t('common.operationFailed'));
        } finally {
          setConfirmLoading(false);
        }
      });
    };

    const handleCancel = () => {
      setVisible(false);
      setSelectedIcon(DEFAULT_ICON);
      setChildren([]);
      setDataLoading(false);
      formRef.current?.resetFields();
    };

    const handleIconSelect = (icon: string) => {
      setSelectedIcon(icon);
      setIconPopoverOpen(false);
    };

    const addChildObject = () => {
      setChildren([...children, { id: '', name: '' }]);
    };

    const removeChildObject = (index: number) => {
      const newChildren = [...children];
      newChildren.splice(index, 1);
      setChildren(newChildren);
    };

    const updateChildObject = (
      index: number,
      field: keyof ChildObject,
      value: string
    ) => {
      const newChildren = [...children];
      newChildren[index] = { ...newChildren[index], [field]: value };
      setChildren(newChildren);
    };

    // 图标选择器内容
    const iconSelectorContent = (
      <div className="w-[320px] max-h-[240px] overflow-y-auto p-2 grid grid-cols-6 gap-2">
        {ICON_LIST.map((icon) => (
          <div
            key={icon}
            className={`w-10 h-10 flex items-center justify-center rounded cursor-pointer border-2 transition-all
            ${
              selectedIcon === icon
                ? 'border-[#1890ff] bg-[#e6f4ff]'
                : 'border-transparent bg-[var(--color-bg-1)] hover:border-[#1890ff] hover:bg-[#e6f4ff]'
            }`}
            onClick={() => handleIconSelect(icon)}
            title={icon.split('_')[1] || icon}
          >
            <img
              src={`/assets/icons/${icon}.svg`}
              alt={icon}
              className="w-6 h-6"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = 'none';
              }}
            />
          </div>
        ))}
      </div>
    );

    // 是否禁用确认按钮
    const isConfirmDisabled = dataLoading || confirmLoading;
    const isBuiltin = type === 'edit' && formData.is_builtin;

    return (
      <OperateModal
        width={600}
        title={title}
        visible={visible}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              className="mr-2"
              type="primary"
              loading={confirmLoading}
              disabled={isConfirmDisabled}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Spin spinning={dataLoading}>
          <Form
            ref={formRef}
            name="objectForm"
            labelCol={{ span: 5 }}
            wrapperCol={{ span: 18 }}
          >
            <Form.Item<ObjectFormData>
              label={t('monitor.object.objectId')}
              name="name"
              rules={[
                { required: true, message: t('common.inputRequired') },
                {
                  pattern: /^[a-zA-Z][a-zA-Z0-9_]*$/,
                  message: t('monitor.object.objectIdPattern')
                }
              ]}
            >
              <Input
                placeholder={t('monitor.object.objectIdPlaceholder')}
                disabled={type === 'edit'}
              />
            </Form.Item>

            <Form.Item<ObjectFormData>
              label={t('monitor.object.displayName')}
              name="display_name"
              rules={[{ required: true, message: t('common.inputRequired') }]}
            >
              <Input
                placeholder={t('monitor.object.displayNamePlaceholder')}
                disabled={isBuiltin}
              />
            </Form.Item>

            <Form.Item label={t('monitor.object.icon')} required={!isBuiltin}>
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 flex items-center justify-center rounded-lg bg-[var(--color-fill-2)]">
                  <img
                    src={`/assets/icons/${selectedIcon}.svg`}
                    alt={selectedIcon}
                    className="w-8 h-8"
                    onError={(e) => {
                      (e.target as HTMLImageElement).src =
                        '/assets/icons/cc-default_默认.svg';
                    }}
                  />
                </div>
                <Popover
                  content={iconSelectorContent}
                  title={t('monitor.object.selectIcon')}
                  trigger="click"
                  open={iconPopoverOpen}
                  onOpenChange={setIconPopoverOpen}
                  placement="bottomLeft"
                >
                  <Button disabled={isBuiltin}>
                    {t('monitor.object.selectIcon')}
                  </Button>
                </Popover>
              </div>
            </Form.Item>

            <Form.Item<ObjectFormData>
              label={t('monitor.object.description')}
              name="description"
            >
              <Input.TextArea
                rows={2}
                placeholder={t('monitor.object.descriptionPlaceholder')}
                disabled={isBuiltin}
              />
            </Form.Item>

            <Form.Item<ObjectFormData>
              label={t('monitor.object.cleanupPolicy')}
              name="cleanup_policy"
              rules={[{ required: true }]}
            >
              <Radio.Group>
                <Radio value="no_cleanup">
                  {t('monitor.object.noCleanup')}
                </Radio>
                <Radio value="timeout">
                  {t('monitor.object.timeoutCleanup')}
                </Radio>
              </Radio.Group>
            </Form.Item>

            <Form.Item
              noStyle
              shouldUpdate={(previous, current) =>
                previous.cleanup_policy !== current.cleanup_policy ||
                previous.cleanup_timeout_days !== current.cleanup_timeout_days
              }
            >
              {({ getFieldValue }) =>
                getFieldValue('cleanup_policy') === 'timeout' && (
                  <Form.Item<ObjectFormData>
                    label={t('monitor.object.timeoutDays')}
                    name="cleanup_timeout_days"
                    extra={t('monitor.object.cleanupPolicyHint', undefined, {
                      days: getFieldValue('cleanup_timeout_days') || 1
                    })}
                    rules={[
                      { required: true, message: t('common.inputRequired') }
                    ]}
                  >
                    <InputNumber
                      min={1}
                      max={365}
                      precision={0}
                      className="w-full"
                    />
                  </Form.Item>
                )
              }
            </Form.Item>

            {/* 子对象：新增和编辑都可以添加/修改 */}
            {!isBuiltin && (
              <Form.Item label={t('monitor.object.childObjects')}>
                <div className="flex flex-col gap-2">
                {children.map((child, index) => {
                  // 判断是否为已存在的子对象（编辑模式下从后端加载的）
                  const isExisting = type === 'edit' && child._isExisting;
                  return (
                    <div
                      key={index}
                      className="flex items-center gap-2 p-2 bg-[var(--color-fill-1)] rounded border border-[var(--color-border-2)]"
                    >
                      <Input
                        className="flex-1"
                        placeholder={t('monitor.object.childIdPlaceholder')}
                        value={child.id}
                        onChange={(e) =>
                          updateChildObject(index, 'id', e.target.value)
                        }
                        disabled={isExisting}
                      />
                      <Input
                        className="flex-1"
                        placeholder={t('monitor.object.childNamePlaceholder')}
                        value={child.name}
                        onChange={(e) =>
                          updateChildObject(index, 'name', e.target.value)
                        }
                      />
                      {!isExisting && (
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<CloseOutlined />}
                          onClick={() => removeChildObject(index)}
                        />
                      )}
                    </div>
                  );
                })}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={addChildObject}
                  className="mt-1"
                >
                  {t('monitor.object.addChildObject')}
                </Button>
                </div>
              </Form.Item>
            )}
          </Form>
        </Spin>
      </OperateModal>
    );
  }
);

ObjectModal.displayName = 'ObjectModal';
export default ObjectModal;
