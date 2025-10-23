'use client';

import React, { forwardRef, useImperativeHandle, useState } from 'react';
import {
  Form,
  Input,
  Select,
  Button,
  Row,
  Col,
  Card,
  message,
  Divider,
  Tooltip
} from 'antd';
import { QuestionCircleOutlined, PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';
import useLabEnv from '@/app/lab/api/env';
import type { ModalRef } from '@/app/lab/types';

const { Option } = Select;

interface InfraInstanceModalProps {
  onSuccess?: (instance: any, operation?: 'create' | 'update') => void;
  imagesList: any[]
}

interface InfraInstanceFormData {
  id?: number | string;
  name: string;
  image: number | string;
  env_vars: Record<string, string>;
  command: string[];
  args: string[];
  port_mappings: Record<string, string>;
  volume_mounts: Array<{
    host_path: string;
    container_path: string;
    read_only?: boolean;
  }>;
  persistent_dirs: string[];
  cpu_limit?: string;
  memory_limit?: string;
  extra_params: Record<string, any>;
}

const InfraInstanceModal = forwardRef<ModalRef, InfraInstanceModalProps>(({ imagesList, onSuccess }, ref) => {
  const { t } = useTranslation();
  const { addInstance, updateInstance } = useLabEnv();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [editData, setEditData] = useState<InfraInstanceFormData | null>(null);
  const [form] = Form.useForm();

  useImperativeHandle(ref, () => ({
    showModal: async (config: any) => {
      const data = config?.form as InfraInstanceFormData;
      setEditData(data || null);
      setOpen(true);

      if (data) {
        // 编辑模式，填充表单数据
        form.setFieldsValue({
          ...data,
          env_vars_pairs: Object.entries(data.env_vars || {}).map(([key, value]) => ({ key, value })),
          command_pairs: (data.command || []).map((cmd: string) => ({ command: cmd })),
          args_pairs: (data.args || []).map((arg: string) => ({ arg })),
          port_mapping_pairs: Object.entries(data.port_mappings || {}).map(([container_port, host_port]) => ({ container_port, host_port })),
          volume_mounts: (data.volume_mounts || []).map((mount: any) => ({
            host_path: mount.host_path,
            container_path: mount.container_path,
            read_only: mount.read_only
          })),
          persistent_dir_pairs: (data.persistent_dirs || []).map((dir: string) => ({ dir }))
        });
      } else {
        // 新建模式，重置表单
        form.resetFields();
        form.setFieldsValue({
          env_vars_pairs: [],
          command_pairs: [],
          args_pairs: [],
          port_mapping_pairs: [],
          volume_mounts: [],
          persistent_dir_pairs: []
        });
      }
    }
  }));

  const handleSubmit = async () => {
    try {
      setLoading(true);
      const values = await form.validateFields();

      // 处理环境变量格式
      const env_vars: Record<string, string> = {};
      if (values.env_vars_pairs) {
        values.env_vars_pairs.forEach((pair: { key: string; value: string }) => {
          if (pair.key && pair.value) {
            env_vars[pair.key] = pair.value;
          }
        });
      }

      // 处理启动命令格式
      const command: string[] = [];
      if (values.command_pairs) {
        values.command_pairs.forEach((pair: { command: string }) => {
          if (pair.command) {
            command.push(pair.command);
          }
        });
      }

      // 处理启动参数格式
      const args: string[] = [];
      if (values.args_pairs) {
        values.args_pairs.forEach((pair: { arg: string }) => {
          if (pair.arg) {
            args.push(pair.arg);
          }
        });
      }

      // 处理端口映射格式
      const port_mappings: Record<string, string> = {};
      if (values.port_mapping_pairs) {
        values.port_mapping_pairs.forEach((pair: { container_port: string; host_port: string }) => {
          if (pair.container_port && pair.host_port) {
            port_mappings[pair.container_port] = pair.host_port;
          }
        });
      }

      // 处理持久化目录格式
      const persistent_dirs: string[] = [];
      if (values.persistent_dir_pairs) {
        values.persistent_dir_pairs.forEach((pair: { dir: string }) => {
          if (pair.dir) {
            persistent_dirs.push(pair.dir);
          }
        });
      }

      const formData: InfraInstanceFormData = {
        name: values.name,
        image: values.image,
        env_vars,
        command,
        args,
        port_mappings,
        volume_mounts: values.volume_mounts || [],
        persistent_dirs,
        cpu_limit: values.cpu_limit,
        memory_limit: values.memory_limit,
        extra_params: {}
      };

      console.log('提交基础设施实例数据:', formData);

      let result;
      const operation = editData ? 'update' : 'create';
      
      if (editData) {
        // 编辑模式
        result = await updateInstance(editData?.id as string, formData);
        message.success('基础设施实例更新成功');
      } else {
        // 新建模式
        result = await addInstance(formData);
        console.log(result);
        message.success('基础设施实例创建成功');
      }

      setOpen(false);
      form.resetFields();
      setEditData(null);
      onSuccess?.(result, operation);

    } catch (error) {
      console.error('操作失败:', error);
      message.error('操作失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setOpen(false);
    form.resetFields();
    setEditData(null);
  };

  return (
    <OperateModal
      title={editData ? '编辑基础设施实例' : '创建基础设施实例'}
      open={open}
      onCancel={handleCancel}
      width={500}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          {t(`common.cancel`)}
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          {t(`common.confirm`)}
        </Button>
      ]}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
      >
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="name"
              label="实例名称"
              rules={[
                { required: true, message: '请输入实例名称' },
                { max: 100, message: '实例名称不能超过100个字符' }
              ]}
            >
              <Input placeholder="请输入实例名称" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="image"
              label="基础设施镜像"
              rules={[{ required: true, message: '请选择基础设施镜像' }]}
            >
              <Select
                placeholder="请选择基础设施镜像"
                showSearch
                filterOption={(input, option) => {
                  const label = option?.label || '';
                  return (label as string).toLowerCase().includes(input.toLowerCase());
                }}
              >
                {imagesList.filter(image => image.image_type === 'infra').map(image => (
                  <Option key={image.id} value={image.id}>
                    {image.name} ({image.version})
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        {/* <Divider orientation="left" orientationMargin={0}>资源限制</Divider> */}

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="cpu_limit"
              label={
                <span>
                  CPU限制
                  <Tooltip title="CPU资源限制，例如: 1, 0.5, 2">
                    <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
                  </Tooltip>
                </span>
              }
            >
              <Input placeholder="例如: 1" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="memory_limit"
              label={
                <span>
                  内存限制
                  <Tooltip title="内存资源限制，例如: 1Gi, 512Mi">
                    <QuestionCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: '14px' }} />
                  </Tooltip>
                </span>
              }
            >
              <Input placeholder="例如: 1Gi" />
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

        <Divider orientation="left" orientationMargin={0}>运行时配置</Divider>

        {/* 环境变量 */}
        <Card title="环境变量" size="small" style={{ marginBottom: 16 }}>
          <Form.List name="env_vars_pairs">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="top" className="mb-2">
                    <Col span={10}>
                      <Form.Item
                        {...restField}
                        name={[name, 'key']}
                        rules={[{ required: true, message: '请输入变量名' }]}
                      >
                        <Input placeholder="变量名" />
                      </Form.Item>
                    </Col>
                    <Col span={10}>
                      <Form.Item
                        {...restField}
                        name={[name, 'value']}
                        rules={[{ required: true, message: '请输入变量值' }]}
                      >
                        <Input placeholder="变量值" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ color: '#ff4d4f', fontSize: '16px', marginTop: '8px' }}
                      />
                    </Col>
                  </Row>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    添加环境变量
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Card>

        {/* 启动命令 */}
        <Card title="启动命令" size="small" style={{ marginBottom: 16 }}>
          <Form.List name="command_pairs">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="top" className="mb-2">
                    <Col span={20}>
                      <Form.Item
                        {...restField}
                        name={[name, 'command']}
                        rules={[{ required: true, message: '请输入启动命令' }]}
                      >
                        <Input placeholder="例如: /bin/bash" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ color: '#ff4d4f', fontSize: '16px', marginTop: '8px' }}
                      />
                    </Col>
                  </Row>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    添加启动命令
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Card>

        {/* 启动参数 */}
        <Card title="启动参数" size="small" style={{ marginBottom: 16 }}>
          <Form.List name="args_pairs">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="top" className="mb-2">
                    <Col span={20}>
                      <Form.Item
                        {...restField}
                        name={[name, 'arg']}
                        rules={[{ required: true, message: '请输入启动参数' }]}
                      >
                        <Input placeholder="例如: --port=8080" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ color: '#ff4d4f', fontSize: '16px', marginTop: '8px' }}
                      />
                    </Col>
                  </Row>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    添加启动参数
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Card>

        <Divider orientation="left" orientationMargin={0}>网络和存储配置</Divider>

        {/* 端口映射 */}
        <Card title="端口映射" size="small" style={{ marginBottom: 16 }}>
          <Form.List name="port_mapping_pairs">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="top" className="mb-2">
                    <Col span={10}>
                      <Form.Item
                        {...restField}
                        name={[name, 'container_port']}
                        rules={[
                          { required: true, message: '请输入容器端口' },
                          { pattern: /^\d+$/, message: '请输入有效的端口号' }
                        ]}
                      >
                        <Input placeholder="容器端口" />
                      </Form.Item>
                    </Col>
                    <Col span={10}>
                      <Form.Item
                        {...restField}
                        name={[name, 'host_port']}
                        rules={[
                          { required: true, message: '请输入主机端口' },
                          { pattern: /^\d+$/, message: '请输入有效的端口号' }
                        ]}
                      >
                        <Input placeholder="主机端口" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ color: '#ff4d4f', fontSize: '16px', marginTop: '8px' }}
                      />
                    </Col>
                  </Row>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    添加端口映射
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Card>

        {/* 卷挂载配置 */}
        <Card title="卷挂载配置" size="small" style={{ marginBottom: 16 }}>
          <Form.List name="volume_mounts">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="top" className="mb-2">
                    <Col span={8}>
                      <Form.Item
                        {...restField}
                        name={[name, 'host_path']}
                        rules={[{ required: true, message: '请输入主机路径' }]}
                      >
                        <Input placeholder="主机路径" />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item
                        {...restField}
                        name={[name, 'container_path']}
                        rules={[{ required: true, message: '请输入容器路径' }]}
                      >
                        <Input placeholder="容器路径" />
                      </Form.Item>
                    </Col>
                    <Col span={5}>
                      <Form.Item
                        {...restField}
                        name={[name, 'read_only']}
                      >
                        <Select placeholder="权限" style={{ width: '100%' }}>
                          <Option value={false}>读写</Option>
                          <Option value={true}>只读</Option>
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={3}>
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ color: '#ff4d4f', fontSize: '16px', marginTop: '8px' }}
                      />
                    </Col>
                  </Row>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    添加卷挂载
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Card>

        {/* 持久化目录 */}
        <Card title="持久化目录" size="small" style={{ marginBottom: 16 }}>
          <Form.List name="persistent_dir_pairs">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <Row key={key} gutter={8} align="top" className="mb-2">
                    <Col span={20}>
                      <Form.Item
                        {...restField}
                        name={[name, 'dir']}
                        rules={[{ required: true, message: '请输入目录路径' }]}
                      >
                        <Input placeholder="容器内目录路径" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <MinusCircleOutlined
                        onClick={() => remove(name)}
                        style={{ color: '#ff4d4f', fontSize: '16px', marginTop: '8px' }}
                      />
                    </Col>
                  </Row>
                ))}
                <Form.Item>
                  <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                    添加持久化目录
                  </Button>
                </Form.Item>
              </>
            )}
          </Form.List>
        </Card>
      </Form>
    </OperateModal>
  );
});

InfraInstanceModal.displayName = 'InfraInstanceModal';
export default InfraInstanceModal;
