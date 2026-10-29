'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Modal, Select, Space, Upload, message } from 'antd';
import Cookies from 'js-cookie';
import CustomTable from '@/components/custom-table';
import { useCustomCollectPluginApi } from '@/app/cmdb/api/customCollectPlugin';
import { useModelApi } from '@/app/cmdb/api';
import ScriptCodeEditor, { ShellSwitch } from './scriptCodeEditor';

const OUTPUT_HINT = `脚本向 stdout 输出 JSON 数组，每条记录必须有 inst_name，字段名与模型属性一致。
示例：[{"inst_name":"192.168.1.10-demo","ip_addr":"192.168.1.10","port":"8080"}]`;

const SCRIPT_FILE_TYPES: Record<string, { accept: string; label: string }> = {
  bash: { accept: '.sh,.bash', label: '.sh、.bash' },
  sh: { accept: '.sh', label: '.sh' },
  powershell: { accept: '.ps1', label: '.ps1' },
  bat: { accept: '.bat,.cmd', label: '.bat、.cmd' },
};

function scriptFileType(shell: string) {
  return SCRIPT_FILE_TYPES[shell] || SCRIPT_FILE_TYPES.bash;
}

function scriptFileMatches(name: string, shell: string) {
  const extension = name.includes('.') ? name.slice(name.lastIndexOf('.')).toLowerCase() : '';
  return scriptFileType(shell).accept.split(',').includes(extension);
}

interface PluginRow {
  id: number;
  name: string;
  plugin_id: string;
  model_id: string;
  os_type: string;
  shell: string;
  version: number;
  updated_at?: string | null;
  reference_count?: number;
  content?: string;
  desc?: string;
  team?: number[];
}

const emptyForm = {
  name: '',
  plugin_id: '',
  model_id: '',
  os_type: 'linux',
  shell: 'bash',
  content: '',
  desc: '',
};

function formatVersionLabel(version: number, versionedAt?: string | null) {
  if (!versionedAt) {
    return `v${version}`;
  }
  const date = new Date(versionedAt.replace(/([+-]\d{2})(\d{2})$/, '$1:$2'));
  if (Number.isNaN(date.getTime())) {
    return `v${version}`;
  }
  const pad = (value: number) => String(value).padStart(2, '0');
  const stamp = `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
  return `${stamp}_v${version}`;
}

function stripPluginPrefix(pluginId: string) {
  return pluginId.startsWith('custom_') ? pluginId.slice('custom_'.length) : pluginId;
}

export default function PluginManager({ lockedModelId = '' }: { lockedModelId?: string }) {
  const api = useCustomCollectPluginApi();
  const { getModelList } = useModelApi();
  const [rows, setRows] = useState<PluginRow[]>([]);
  const [models, setModels] = useState<Array<{ label: string; value: string }>>([]);
  const [uploadedName, setUploadedName] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<PluginRow | null>(null);
  const [form] = Form.useForm();
  const osType = Form.useWatch('os_type', form) || 'linux';
  const shell = Form.useWatch('shell', form) || 'bash';
  const fileType = scriptFileType(shell);

  const applyShell = (next: string) => {
    form.setFieldValue('shell', next);
    if (uploadedName && !scriptFileMatches(uploadedName, next)) {
      form.setFieldValue('content', '');
      setUploadedName('');
      message.warning(`已清除已选文件，当前只接受 ${scriptFileType(next).label}`);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const response = await api.listPlugins({ page_size: 200 });
      const data = response?.items || response?.results || [];
      const list = Array.isArray(data) ? data : [];
      setRows(lockedModelId ? list.filter((item) => item.model_id === lockedModelId) : list);
    } catch {
      message.error('加载自定义插件失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    getModelList()
      .then((data) => {
        setModels((data || []).map((item: { model_id: string; model_name?: string }) => ({
          label: item.model_name || item.model_id,
          value: item.model_id,
        })));
      })
      .catch(() => setModels([]));
    // getModelList 每次渲染都是新引用，不能放进依赖。
  }, [lockedModelId]);

  const openCreate = () => {
    setEditing(null);
    setUploadedName('');
    form.setFieldsValue({ ...emptyForm, model_id: lockedModelId, content: '' });
    setOpen(true);
  };

  const openEdit = async (row: PluginRow) => {
    try {
      const detail = await api.getPlugin(row.id);
      setEditing({ ...row, ...detail });
      form.setFieldsValue({
        ...row,
        ...detail,
        plugin_id: stripPluginPrefix(detail.plugin_id || row.plugin_id),
        content: detail.content || '',
      });
      setUploadedName('');
      setOpen(true);
    } catch (error: any) {
      message.error(error?.message || '加载脚本失败');
    }
  };

  const save = async () => {
    const values = await form.validateFields();
    if (!editing && !values.content) {
      message.error(`请上传 ${scriptFileType(values.shell).label} 脚本文件`);
      return;
    }
    const teamId = Number(Cookies.get('current_team'));
    const payload = {
      name: values.name,
      plugin_id: values.plugin_id,
      model_id: lockedModelId || values.model_id,
      os_type: values.os_type,
      shell: values.shell,
      content: values.content,
      desc: values.desc || '',
      team: editing?.team?.length ? editing.team : [teamId],
    };
    try {
      if (editing) {
        await api.updatePlugin(editing.id, payload);
      } else {
        await api.createPlugin(payload);
      }
      message.success('已保存，引用中的任务将在下一轮采集使用新脚本');
      setOpen(false);
      load();
    } catch (error: any) {
      message.error(error?.message || '保存失败');
    }
  };

  return (
    <div className="p-4">
      <div className="mb-3 flex justify-between">
        <div className="text-sm text-[var(--color-text-2)]">新建插件请上传脚本。编辑时可以在表单里改脚本，也可以重新上传覆盖。</div>
        <Button type="primary" onClick={openCreate}>新建插件</Button>
      </div>
      <CustomTable
        loading={loading}
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '标识', dataIndex: 'plugin_id' },
          { title: '模型', dataIndex: 'model_id' },
          { title: '系统', dataIndex: 'os_type' },
          {
            title: '版本',
            dataIndex: 'version',
            render: (_value: number, row: PluginRow) => formatVersionLabel(row.version, row.updated_at),
          },
          { title: '引用', dataIndex: 'reference_count' },
          {
            title: '操作',
            render: (_value, row: PluginRow) => (
              <Space>
                <Button type="link" onClick={() => openEdit(row)}>编辑</Button>
                <Button
                  type="link"
                  danger
                  onClick={() => {
                    Modal.confirm({
                      title: '删除插件',
                      content: '被采集任务引用的插件无法删除。',
                      onOk: async () => {
                        await api.deletePlugin(row.id);
                        load();
                      },
                    });
                  }}
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? '编辑自定义插件' : '新建自定义插件'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={save}
        width={760}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item
            name="plugin_id"
            label="标识"
            extra="只需填写后缀，保存时自动加上 custom_ 前缀"
            rules={[{ required: true, message: '请填写标识' }]}
          >
            <Input disabled={Boolean(editing)} placeholder="host_scan" />
          </Form.Item>
          <Form.Item name="model_id" label="目标模型" rules={[{ required: true, message: '请选择目标模型' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              disabled={Boolean(lockedModelId || editing)}
              options={models}
              placeholder="选择已有模型"
            />
          </Form.Item>
          <Form.Item name="os_type" label="操作系统" rules={[{ required: true }]}>
            <Select
              disabled={Boolean(editing)}
              options={[{ value: 'linux', label: 'Linux' }, { value: 'windows', label: 'Windows' }]}
              onChange={(value: 'linux' | 'windows') => {
                applyShell(value === 'windows' ? 'powershell' : 'bash');
              }}
            />
          </Form.Item>
          <Form.Item name="shell" hidden rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <div className="mb-2">
            <ShellSwitch osType={osType} value={shell} onChange={applyShell} />
          </div>
          {editing ? (
            <Form.Item name="content" label="脚本" rules={[{ required: true, message: '请填写或上传脚本' }]} extra={OUTPUT_HINT}>
              <ScriptCodeEditor shell={shell} />
            </Form.Item>
          ) : (
            <Form.Item label="脚本" required extra={uploadedName ? `已选择 ${uploadedName}，确认保存后生效` : `新建只能上传 ${fileType.label} 脚本文件`}>
              <Form.Item name="content" noStyle rules={[{ required: true, message: `请上传 ${fileType.label} 脚本文件` }]}>
                <Input type="hidden" />
              </Form.Item>
            </Form.Item>
          )}
          <Upload
            accept={fileType.accept}
            showUploadList={false}
            beforeUpload={(file) => {
              if (!scriptFileMatches(file.name, shell)) {
                message.error(`请上传 ${fileType.label} 脚本文件`);
                return Upload.LIST_IGNORE;
              }
              file.text().then((text) => {
                form.setFieldValue('content', text);
                setUploadedName(file.name);
              });
              return false;
            }}
          >
            <Button>{editing ? '上传并覆盖脚本' : '上传脚本'}</Button>
          </Upload>
          <div className="mb-4 mt-1 text-xs text-[var(--color-text-3)]">{`当前脚本类型：${shell}（${fileType.label}）`}</div>
          <Form.Item name="desc" label="描述"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
