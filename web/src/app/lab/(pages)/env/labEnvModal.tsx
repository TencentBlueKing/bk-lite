'use client';

import React, { forwardRef, useImperativeHandle, useState } from 'react';
import {
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  Row,
  Col,
  message,
  Divider,
  Tooltip
} from 'antd';
import { QuestionCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useLabEnv from '@/app/lab/api/env';
import useLabManage from '@/app/lab/api/mirror';
import InfraInstanceModal from './infraInstanceModal';
import type { ModalRef } from '@/app/lab/types';

const { TextArea } = Input;
const { Option } = Select;

interface LabEnvProps {
  onSuccess?: () => void;
}

interface LabEnvFormData {
  id?: number | string;
  name: string;
  description?: string;
  ide_image: number | string;
  infra_instances: (number | string)[];
  infra_instances_info?: any[];
  cpu: number;
  memory: string;
  gpu: number;
  volume_size: string;
  state?: string;
  endpoint?: string;
}

interface LabImageOption {
  id: number | string;
  name: string;
  version: string;
  image_type: 'ide' | 'infra';
}

interface InfraInstanceOption {
  id: number | string;
  name: string;
  status: string;
  image: number;
  image_name: string;
  image_version: string;
  cpu_limit?: string;
  memory_limit?: string;
  port_mappings?: Record<string, string>;
}



const LabEnvModal = forwardRef<ModalRef, LabEnvProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const { addEnv, updateEnv, getInstanceList } = useLabEnv();
  const { getImageList } = useLabManage();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editData, setEditData] = useState<LabEnvFormData | null>(null);
  const [form] = Form.useForm();
  const [imagesList, setImagesList] = useState<LabImageOption[]>([]); // 全部的镜像 
  const [infraInstances, setInfraInstances] = useState<InfraInstanceOption[]>([]); // 全部的基础设施实例
  const [curEnvInstances, setCurEnvInstances] = useState<(string | number)[]>([]); // 当前环境下的实例ID
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const infraInstanceModalRef = React.useRef<ModalRef>(null);

  useImperativeHandle(ref, () => ({
    showModal: async (config: any) => {
      const data = config?.form as LabEnvFormData;
      setEditData(data || null);
      setCurEnvInstances(data?.infra_instances);
      setOpen(true);

      if (data) {
        // 编辑模式，填充表单数据
        form.setFieldsValue({
          ...data,
          infra_instances: data.infra_instances || []
        });
      } else {
        // 新建模式，重置表单
        form.resetFields();
        setCurEnvInstances([]);
        form.setFieldsValue({
          cpu: 2,
          memory: '4Gi',
          gpu: 0,
          volume_size: '50Gi',
          infra_instances: []
        });
      }

      // 首次打开或需要完整数据时才加载
      if (!isInitialized || imagesList.length === 0 || infraInstances.length === 0) {
        // 在后台异步加载选项数据，不阻塞弹窗显示
        loadOptions(false);
      }
    }
  }));

  const loadOptions = async (forceRefresh = false) => {
    try {
      setLoadingOptions(true);

      // 并行加载数据，避免阻塞
      const promises = [];

      // 只有在数据为空或强制刷新时才加载 IDE 镜像
      if (imagesList.length === 0 || forceRefresh) {
        promises.push(
          getImageList().then(response => {
            setImagesList(response || []);
            console.log('IDE镜像:', response);
          })
        );
      }

      // 只有在数据为空或强制刷新时才加载基础设施实例
      if (infraInstances.length === 0 || forceRefresh) {
        promises.push(
          getInstanceList().then(response => {
            setInfraInstances(response || []);
            console.log('基础设施实例:', response);
          })
        );
      }

      await Promise.all(promises);

      if (!isInitialized) {
        setIsInitialized(true);
      }

    } catch (error) {
      console.error('加载选项数据失败:', error);
      message.error(t(`lab.manage.loadOptionsFailed`));
    } finally {
      setLoadingOptions(false);
    }
  };

  const handleSubmit = async () => {
    try {
      setLoading(true);
      const values = await form.validateFields();

      const formData: LabEnvFormData = {
        name: values.name,
        description: values.description,
        ide_image: values.ide_image,
        infra_instances: curEnvInstances || [],
        cpu: values.cpu,
        memory: values.memory,
        gpu: values.gpu,
        volume_size: values.volume_size,
        endpoint: values.endpoint
      };

      console.log('提交环境数据:', formData);

      if (editData) {
        // 编辑模式
        await updateEnv(editData?.id as string, formData);
        message.success(t(`lab.manage.envUpdatedSuccess`));
      } else {
        // 新建模式
        await addEnv(formData);
        message.success(t(`lab.manage.envCreatedSuccess`));
      }

      setOpen(false);
      form.resetFields();
      setEditData(null);
      onSuccess?.();

    } catch (error) {
      console.error(t(`common.valFailed`), error);
      message.error(t(`lab.manage.operationFailed`));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    form.resetFields();
    setEditData(null);
  };

  // 验证内存格式
  const validateMemoryFormat = (_: any, value: string) => {
    if (!value) return Promise.resolve();
    const memoryPattern = /^(\d+)([MmGgTt][Ii]?)$/;
    if (!memoryPattern.test(value)) {
      return Promise.reject(new Error(t(`lab.manage.memoryFormat`)));
    }
    return Promise.resolve();
  };

  // 验证存储格式
  const validateVolumeFormat = (_: any, value: string) => {
    if (!value) return Promise.resolve();
    const volumePattern = /^(\d+)([MmGgTt][Ii]?)$/;
    if (!volumePattern.test(value)) {
      return Promise.reject(new Error(t(`lab.manage.volumeFormat`)));
    }
    return Promise.resolve();
  };

  // 处理基础设施实例操作成功（创建或更新）
  const handleInfraInstanceSuccess = async (instance: any, operation: 'create' | 'update' = 'create') => {
    try {
      // 刷新基础设施实例数据
      const infraInstancesResponse = await getInstanceList();
      setInfraInstances(infraInstancesResponse || []);
      
      if (operation === 'create') {
        // 创建操作：添加新实例到当前选择列表
        const newInstances = Array.from(new Set([...curEnvInstances, instance.id]));
        setCurEnvInstances(newInstances);
        
        // 同步更新表单值
        form.setFieldsValue({ infra_instances: newInstances });
        
        console.log('创建实例成功，已添加到选择列表:', instance);
        // message.success(`实例 "${instance.name || instance.id}" 已创建并添加到环境中`);
      } else {
        // 更新操作：仅刷新数据，保持当前选择状态
        console.log('更新实例成功，已刷新实例信息:', instance);
        // message.success(`实例 "${instance.name || instance.id}" 更新成功`);
      }
      
      // 强制重新渲染已选择的实例卡片以显示最新信息
      setCurEnvInstances(prev => [...prev]);
      
    } catch (error) {
      const action = operation === 'create' ? '创建' : '更新';
      console.error(`处理${action}实例失败:`, error);
      message.error(`处理${action}实例失败`);
    }
  };

  // 打开基础设施实例创建弹窗
  const handleCreateInfraInstance = () => {
    infraInstanceModalRef.current?.showModal({ type: 'add' });
  };

  const getStatusStyle = (status: string) => {
    switch (status) {
      case 'running':
        return { color: '#52c41a', bgColor: '#f6ffed', text: '运行中' };
      case 'stopped':
        return { color: '#ff4d4f', bgColor: '#fff2f0', text: '已停止' };
      case 'pending':
        return { color: '#faad14', bgColor: '#fffbe6', text: '启动中' };
      default:
        return { color: '#8c8c8c', bgColor: '#f5f5f5', text: status };
    }
  };

  // 处理实例卡片点击编辑
  const handleEditInstance = (instanceId: number | string) => {
    // 在 infraInstances 中查找对应的完整实例信息
    const instanceData = infraInstances.find(instance => instance.id === instanceId);

    if (instanceData) {
      // 调出编辑弹窗，传入完整的实例数据
      infraInstanceModalRef.current?.showModal({
        type: 'edit',
        form: instanceData
      });
    } else {
      console.warn('未找到对应的实例数据:', instanceId);
      message.warning('未找到实例详细信息');
    }
  };

  // 根据状态设置对应的 Tailwind 类名
  const getStatusClasses = (status: string) => {
    switch (status) {
      case 'running':
        return 'text-green-600 bg-green-50 border-green-200';
      case 'stopped':
        return 'text-red-600 bg-red-50 border-red-200';
      case 'pending':
        return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const renderSelectedInstances = () => {
    if (!curEnvInstances || curEnvInstances.length === 0) return null;

    return curEnvInstances.map(id => {
      const instance = infraInstances.find(item => item.id === id);
      const image = imagesList.find(img => img.id === instance?.image);
      
      if (!instance) {
        return (
          <div key={id} className="p-2 bg-red-50 border border-red-200 rounded text-red-600 text-sm">
            实例不存在 (ID: {id})
          </div>
        );
      }

      const statusStyle = getStatusStyle(instance.status);
      return (
        <div
          key={instance.id}
          className="relative w-full p-3 border border-gray-200 rounded-lg bg-white shadow-sm hover:shadow-md transition-all duration-200"
        >
          {/* 移除按钮 */}
          <button
            className="absolute top-1 right-1 w-6 h-6 flex items-center justify-center text-gray-400  rounded-full transition-colors"
            onClick={() => {
              const newInstances = curEnvInstances.filter(instanceId => instanceId !== id);
              setCurEnvInstances(newInstances);
              form.setFieldsValue({ infra_instances: newInstances });
            }}
          >
            ×
          </button>

          {/* 实例信息 */}
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-sm text-gray-800 truncate flex-1 pr-6">
              {instance.name}
            </span>
            
          </div>

          {image && (
            <div className="text-xs text-gray-500 mb-2">
              <span className="font-medium">镜像:</span> {image.name}:{image.version}
            </div>
          )}

          {/* 资源信息 */}
          {/* {(instance.cpu_limit || instance.memory_limit) && (
            <div className="text-xs text-gray-500">
              {instance.cpu_limit && <span>CPU: {instance.cpu_limit}</span>}
              {instance.cpu_limit && instance.memory_limit && <span className="mx-1">|</span>}
              {instance.memory_limit && <span>内存: {instance.memory_limit}</span>}
            </div>
          )} */}

          {/* 编辑按钮 */}
          <div className="flex justify-between mt-2">
            <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getStatusClasses(instance.status)}`}>
              {statusStyle.text}
            </span>
            <Button
              type="link"
              size="small"
              onClick={() => handleEditInstance(instance.id)}
              className="text-blue-600 hover:text-blue-700 p-0 h-auto"
            >
              编辑配置
            </Button>
          </div>
        </div>
      );
    });
  };

  return (
    <OperateModal
      title={editData ? t(`lab.manage.editEnvironment`) : t(`lab.manage.addEnvironment`)}
      open={open}
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          {t(`common.cancel`)}
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          {t(`common.confirm`)}
        </Button>
      ]}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          cpu: 2,
          memory: '4Gi',
          gpu: 0,
          volume_size: '50Gi'
        }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="name"
              label={t(`lab.manage.envName`)}
              rules={[
                { required: true, message: t(`lab.manage.envNameRequired`) },
                { max: 100, message: t(`lab.manage.envNameMaxLength`) }
              ]}
            >
              <Input placeholder={t(`lab.manage.enterEnvName`)} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="ide_image"
              label={t(`lab.manage.ideImage`)}
              rules={[{ required: true, message: t(`lab.manage.ideImageRequired`) }]}
            >
              <Select
                placeholder={t(`lab.manage.selectIdeImage`)}
                loading={loadingOptions}
                showSearch
                filterOption={(input, option) => {
                  const label = option?.label || '';
                  return (label as string).toLowerCase().includes(input.toLowerCase());
                }}
              >
                {imagesList.filter(image => image.image_type === 'ide').map(image => (
                  <Option key={image.id} value={image.id}>
                    {image.name} ({image.version})
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="description"
          label={t(`lab.manage.envDescription`)}
        >
          <TextArea
            rows={3}
            placeholder={t(`lab.manage.enterDescription`)}
            maxLength={500}
            showCount
          />
        </Form.Item>

        <Divider orientation="left" orientationMargin={0}>{t(`lab.manage.resourceConfig`)}</Divider>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="cpu"
              label={
                <span>
                  {t(`lab.manage.cpuCores`)}
                  <Tooltip title={t(`lab.manage.cpuTooltip`)}>
                    <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
                  </Tooltip>
                </span>
              }
              rules={[
                { required: true, message: t(`lab.manage.cpuRequired`) },
                { type: 'number', min: 1, max: 32, message: t(`lab.manage.cpuRange`) }
              ]}
            >
              <InputNumber
                min={1}
                max={32}
                placeholder="2"
                style={{ width: '100%' }}
                addonAfter={t(`lab.manage.coreUnit`)}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="memory"
              label={
                <span>
                  {t(`lab.manage.memorySize`)}
                  <Tooltip title={t(`lab.manage.memoryTooltip`)}>
                    <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
                  </Tooltip>
                </span>
              }
              rules={[
                { required: true, message: t(`lab.manage.memoryRequired`) },
                { validator: validateMemoryFormat }
              ]}
            >
              <Input placeholder="4Gi" />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="gpu"
              label={
                <span>
                  {t(`lab.manage.gpuCount`)}
                  <Tooltip title={t(`lab.manage.gpuTooltip`)}>
                    <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
                  </Tooltip>
                </span>
              }
              rules={[
                { required: true, message: t(`lab.manage.gpuRequired`) },
                { type: 'number', min: 0, max: 8, message: t(`lab.manage.gpuRange`) }
              ]}
            >
              <InputNumber
                min={0}
                max={8}
                placeholder="0"
                style={{ width: '100%' }}
                addonAfter={t(`lab.manage.pieceUnit`)}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="volume_size"
              label={
                <span>
                  {t(`lab.manage.volumeSize`)}
                  <Tooltip title={t(`lab.manage.volumeTooltip`)}>
                    <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
                  </Tooltip>
                </span>
              }
              rules={[
                { required: true, message: t(`lab.manage.volumeRequired`) },
                { validator: validateVolumeFormat }
              ]}
            >
              <Input placeholder="50Gi" />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="endpoint"
          label={t('lab.manage.endpoint')}
          rules={[
            { max: 200, message: t('lab.manage.endpointMaxLength') }
          ]}
        >
          <Input placeholder={t('lab.manage.enterEndpoint')} />
        </Form.Item>

        <Divider orientation="left" orientationMargin={0}>{t(`lab.manage.infraConfig`)}</Divider>

        <Form.Item
          label={
            <span>
              {t(`lab.manage.infraInstances`)}
              <Tooltip title={t(`lab.manage.infraTooltip`)}>
                <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
              </Tooltip>
            </span>
          }
        >
          <div>
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              onClick={handleCreateInfraInstance}
              style={{ width: '100%', marginBottom: 16 }}
            >
              创建基础设施实例
            </Button>
            {/* 展示当前环境拥有的实例卡片 */}
            {curEnvInstances && curEnvInstances.length > 0 && (
              <div>
                <div className='flex flex-wrap gap-2'>
                  {renderSelectedInstances()}
                </div>
              </div>
            )}
          </div>
        </Form.Item>
      </Form>

      {/* 基础设施实例创建弹窗 */}
      <InfraInstanceModal
        imagesList={imagesList}
        ref={infraInstanceModalRef}
        onSuccess={(instance, operation) => handleInfraInstanceSuccess(instance, operation)}
      />
    </OperateModal>
  );
});

LabEnvModal.displayName = 'LabEnvModal';
export default LabEnvModal;
