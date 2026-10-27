'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Input, Modal, Select, Space, Upload, message } from 'antd';
import Cookies from 'js-cookie';
import CustomTable from '@/components/custom-table';
import { useCustomCollectPluginApi } from '@/app/cmdb/api/customCollectPlugin';
import { useModelApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import ScriptCodeEditor, { ShellSwitch } from './scriptCodeEditor';

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
  const { t } = useTranslation();
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

  const load = async () => {
    setLoading(true);
    try {
      const response = await api.listPlugins({ page_size: 200 });
      const data = response?.items || response?.results || [];
      const list = Array.isArray(data) ? data : [];
      setRows(lockedModelId ? list.filter((item) => item.model_id === lockedModelId) : list);
    } catch {
      message.error(t('Collection.customPlugin.loadFailed'));
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
      message.error(error?.message || t('Collection.customPlugin.loadScriptFailed'));
    }
  };

  const save = async () => {
    const values = await form.validateFields();
    if (!editing && !values.content) {
      message.error(t('Collection.customPlugin.uploadRequired'));
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
      message.success(t('Collection.customPlugin.saved'));
      setOpen(false);
      load();
    } catch (error: any) {
      message.error(error?.message || t('Collection.customPlugin.saveFailed'));
    }
  };

  return (
    <div className="p-4">
      <div className="mb-3 flex justify-between">
        <div className="text-sm text-[var(--color-text-2)]">{t('Collection.customPlugin.intro')}</div>
        <Button type="primary" onClick={openCreate}>{t('Collection.customPlugin.create')}</Button>
      </div>
      <CustomTable
        loading={loading}
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: t('Collection.customPlugin.name'), dataIndex: 'name' },
          { title: t('Collection.customPlugin.pluginId'), dataIndex: 'plugin_id' },
          { title: t('Collection.customPlugin.model'), dataIndex: 'model_id' },
          { title: t('Collection.customPlugin.os'), dataIndex: 'os_type' },
          {
            title: t('Collection.customPlugin.version'),
            dataIndex: 'version',
            render: (_value: number, row: PluginRow) => formatVersionLabel(row.version, row.updated_at),
          },
          { title: t('Collection.customPlugin.references'), dataIndex: 'reference_count' },
          {
            title: t('Collection.customPlugin.action'),
            render: (_value, row: PluginRow) => (
              <Space>
                <Button type="link" onClick={() => openEdit(row)}>{t('Collection.customPlugin.edit')}</Button>
                <Button
                  type="link"
                  danger
                  onClick={() => {
                    Modal.confirm({
                      title: t('Collection.customPlugin.deleteTitle'),
                      content: t('Collection.customPlugin.deleteContent'),
                      onOk: async () => {
                        await api.deletePlugin(row.id);
                        load();
                      },
                    });
                  }}
                >
                  {t('Collection.customPlugin.delete')}
                </Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing ? t('Collection.customPlugin.editTitle') : t('Collection.customPlugin.createTitle')}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={save}
        width={760}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('Collection.customPlugin.name')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item
            name="plugin_id"
            label={t('Collection.customPlugin.pluginId')}
            extra={t('Collection.customPlugin.pluginIdExtra')}
            rules={[{ required: true, message: t('Collection.customPlugin.pluginIdRequired') }]}
          >
            <Input disabled={Boolean(editing)} placeholder={t('Collection.customPlugin.pluginIdPlaceholder')} />
          </Form.Item>
          <Form.Item name="model_id" label={t('Collection.customPlugin.targetModel')} rules={[{ required: true, message: t('Collection.customPlugin.targetModelRequired') }]}>
            <Select
              showSearch
              optionFilterProp="label"
              disabled={Boolean(lockedModelId || editing)}
              options={models}
              placeholder={t('Collection.customPlugin.targetModelPlaceholder')}
            />
          </Form.Item>
          <Form.Item name="os_type" label={t('Collection.customPlugin.operatingSystem')} rules={[{ required: true }]}>
            <Select
              disabled={Boolean(editing)}
              options={[{ value: 'linux', label: 'Linux' }, { value: 'windows', label: 'Windows' }]}
              onChange={(value: 'linux' | 'windows') => {
                form.setFieldValue('shell', value === 'windows' ? 'powershell' : 'bash');
              }}
            />
          </Form.Item>
          <Form.Item name="shell" hidden rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <div className="mb-2">
            <ShellSwitch osType={osType} value={shell} onChange={(next) => form.setFieldValue('shell', next)} />
          </div>
          {editing ? (
            <Form.Item name="content" label={t('Collection.customPlugin.script')} rules={[{ required: true, message: t('Collection.customPlugin.scriptRequired') }]} extra={t('Collection.customPlugin.outputHint')}>
              <ScriptCodeEditor shell={shell} />
            </Form.Item>
          ) : (
            <Form.Item label={t('Collection.customPlugin.script')} required extra={uploadedName ? t('Collection.customPlugin.selectedFile', undefined, { name: uploadedName }) : t('Collection.customPlugin.createUploadOnly')}>
              <Form.Item name="content" noStyle rules={[{ required: true, message: t('Collection.customPlugin.uploadRequired') }]}>
                <Input type="hidden" />
              </Form.Item>
            </Form.Item>
          )}
          <Upload
            accept=".sh,.ps1,.bash,.bat,.cmd,.txt"
            showUploadList={false}
            beforeUpload={(file) => {
              file.text().then((text) => {
                form.setFieldValue('content', text);
                setUploadedName(file.name);
              });
              return false;
            }}
          >
            <Button>{editing ? t('Collection.customPlugin.uploadReplace') : t('Collection.customPlugin.upload')}</Button>
          </Upload>
          <Form.Item name="desc" label={t('Collection.customPlugin.description')}><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
