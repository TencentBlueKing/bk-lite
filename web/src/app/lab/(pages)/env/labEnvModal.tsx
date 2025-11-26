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
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useLabEnv from '@/app/lab/api/env';
import useLabManage from '@/app/lab/api/mirror';
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
  infra_images: (number | string)[]; // 改为基础设施镜像ID列表
  infra_instances?: (number | string)[]; // 保留用于兼容后端
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



const LabEnvModal = forwardRef<ModalRef, LabEnvProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const { addEnv, updateEnv } = useLabEnv();
  const { getImageList, getInfraImages } = useLabManage();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editData, setEditData] = useState<LabEnvFormData | null>(null);
  const [form] = Form.useForm();
  const [imagesList, setImagesList] = useState<LabImageOption[]>([]); // 全部的镜像
  const [infraImagesList, setInfraImagesList] = useState<LabImageOption[]>([]); // 基础设施镜像列表
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  useImperativeHandle(ref, () => ({
    showModal: async (config: any) => {
      const data = config?.form as LabEnvFormData;
      setEditData(data || null);
      setOpen(true);

      if (data) {
        // 编辑模式，填充表单数据
        // 从 infra_instances_info 中提取镜像ID用于回显
        let infraImageIds: (number | string)[] = [];
        
        if (data.infra_instances_info && data.infra_instances_info.length > 0) {
          // 从实例信息中提取对应的镜像ID
          infraImageIds = data.infra_instances_info
            .map((instance: any) => instance.image || instance.image_id)
            .filter((id: any) => id !== undefined && id !== null);
          
          console.log('从实例信息提取镜像ID:', infraImageIds);
        } else if (data.infra_images && data.infra_images.length > 0) {
          // 如果有 infra_images 字段，直接使用
          infraImageIds = data.infra_images;
        } else if (data.infra_instances && data.infra_instances.length > 0) {
          // 兼容：如果只有 infra_instances，尝试使用（可能不准确）
          infraImageIds = data.infra_instances;
        }
        
        form.setFieldsValue({
          ...data,
          infra_images: infraImageIds
        });
      } else {
        // 新建模式，重置表单
        form.resetFields();
        form.setFieldsValue({
          cpu: 2,
          memory: '4Gi',
          gpu: 0,
          volume_size: '50Gi',
          infra_images: []
        });
      }

      // 首次打开或需要完整数据时才加载
      if (!isInitialized || imagesList.length === 0 || infraImagesList.length === 0) {
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

      // 只有在数据为空或强制刷新时才加载基础设施镜像
      if (infraImagesList.length === 0 || forceRefresh) {
        promises.push(
          getInfraImages().then(response => {
            setInfraImagesList(response || []);
            console.log('基础设施镜像:', response);
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
      console.log(values);
      const image_name = imagesList.find(item => item.id === values?.ide_image)?.name || '';
      const formData: LabEnvFormData = {
        name: values.name,
        description: values.descriptions || image_name,
        ide_image: values.ide_image,
        infra_images: values.infra_images || [],
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
        <Row gutter={24}>
          <Col span={24}>
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
        </Row>

        <Row gutter={24}>
          <Col span={24}>
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
          name="infra_images"
          label={
            <span>
              {t(`lab.manage.infraInstances`)}
              <Tooltip title={t(`lab.manage.infraTooltip`)}>
                <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
              </Tooltip>
            </span>
          }
        >
          <Select
            mode="multiple"
            placeholder="请选择基础设施镜像模板"
            loading={loadingOptions}
            showSearch
            filterOption={(input, option) => {
              const label = option?.label || '';
              return (label as string).toLowerCase().includes(input.toLowerCase());
            }}
          >
            {infraImagesList.map(image => (
              <Option key={image.id} value={image.id} label={`${image.name} (${image.version})`}>
                {image.name} ({image.version})
              </Option>
            ))}
          </Select>
        </Form.Item>
      </Form>
    </OperateModal>
  );
});

LabEnvModal.displayName = 'LabEnvModal';
export default LabEnvModal;
