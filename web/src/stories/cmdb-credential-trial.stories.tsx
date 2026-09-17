import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import { Button, ConfigProvider, Drawer, Form, Input, InputNumber, Modal, Tag, message } from 'antd';
import { EditOutlined, ReloadOutlined } from '@ant-design/icons';
import { IntlProvider } from 'react-intl';
import { CredentialPickerChrome, CredentialQuickCreateForm } from '@/components/credential-picker';
import type { CredentialTypeItem } from '@/components/credential-picker';
import zhCommon from '@/locales/zh.json';
import zhSystem from '@/app/system-manager/locales/zh.json';

function flatten(source: Record<string, unknown>, prefix = ''): Record<string, string> {
  return Object.fromEntries(Object.entries(source).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return value && typeof value === 'object' && !Array.isArray(value)
      ? Object.entries(flatten(value as Record<string, unknown>, path))
      : [[path, String(value)]];
  }));
}

const messages = { ...flatten(zhCommon), ...flatten(zhSystem) };
const samples = [
  { label: '生产 MySQL 只读', value: 'trial-mysql-prod' },
  { label: '预发布 MySQL 账户', value: 'trial-mysql-staging' },
  { label: '数据库巡检账户', value: 'trial-mysql-inventory' },
];
const sqlType: CredentialTypeItem = {
  key: 'sql', name: '用户名密码', categories: ['database'], is_builtin: true,
  fields: [
    { id: 'username', name: '用户名', kind: 'string', required: true },
    { id: 'password', name: '密码', kind: 'secret', required: true },
  ],
};

function CredentialTrial() {
  const [options, setOptions] = useState(samples);
  const [selected, setSelected] = useState<string | undefined>(samples[0].value);
  const [mode, setMode] = useState<'vault' | 'inline'>('inline');
  const [refreshing, setRefreshing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [form] = Form.useForm();
  const [notice, noticeHolder] = message.useMessage();

  const openCreate = () => {
    createForm.resetFields();
    createForm.setFieldsValue({ category: 'database', type: 'sql', group_id: 1, fields: {} });
    setCreateOpen(true);
  };
  const saveCredential = async () => {
    const values = await createForm.validateFields();
    const value = `trial-${crypto.randomUUID()}`;
    setOptions((current) => [...current, { label: values.name, value }]);
    setSelected(value);
    setMode('vault');
    setCreateOpen(false);
    createForm.resetFields();
    void notice.success('已在体验列表新增并选用');
  };
  const refresh = () => {
    setRefreshing(true);
    window.setTimeout(() => {
      setRefreshing(false);
      void notice.success(`已刷新，共 ${options.length} 个凭据`);
    }, 500);
  };
  const reset = () => {
    setOptions(samples);
    setSelected(samples[0].value);
    setMode('inline');
    form.resetFields();
  };

  return (
    <ConfigProvider theme={{ token: { controlHeight: 40, borderRadius: 6 } }}>
      {noticeHolder}
      <main className="min-h-screen bg-[var(--color-fill-1)] px-5 py-8">
        <div className="mx-auto max-w-[760px]">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <h1 className="m-0 text-xl font-semibold text-[var(--color-text-1)]">配置采集 · 凭据选择</h1>
                <Tag color="blue">交互体验</Tag>
              </div>
              <p className="m-0 text-sm text-[var(--color-text-3)]">体验数据，不会创建真实凭据或采集任务。请使用虚构账号密码。</p>
            </div>
            <Button icon={<ReloadOutlined />} onClick={reset}>重置</Button>
          </div>
          <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
            <header className="border-b border-[var(--color-border)] px-6 py-4">
              <h2 className="m-0 text-base font-semibold text-[var(--color-text-1)]">新增 MySQL 采集任务</h2>
            </header>
            <Form form={form} layout="vertical" className="!p-6"
              initialValues={{ name: 'MySQL 配置采集', address: '192.0.2.31', port: 3306, database: 'order' }}>
              <Form.Item label="任务名称" name="name"><Input /></Form.Item>
              <Form.Item label="连接地址" name="address" required><Input /></Form.Item>
              <div className="grid grid-cols-1 gap-x-5 sm:grid-cols-2">
                <Form.Item label="端口" name="port" required><InputNumber className="!w-full" min={1} max={65535} /></Form.Item>
                <Form.Item label="库名" name="database"><Input /></Form.Item>
              </div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="font-medium text-[var(--color-text-1)]">凭据 <span className="text-[var(--color-fail)]">*</span></span>
                <Button type="link" icon={<EditOutlined />} onClick={() => setMode(mode === 'vault' ? 'inline' : 'vault')}>
                  {mode === 'vault' ? '改用手动录入' : '使用已有凭据'}
                </Button>
              </div>
              {mode === 'vault' ? (
                <CredentialPickerChrome value={selected} options={options} loading={refreshing}
                  canAdd canView onChange={setSelected} onRefresh={refresh}
                  onAdd={openCreate} onOpenVault={() => setManageOpen(true)} />
              ) : (
                <div className="grid grid-cols-1 gap-x-5 sm:grid-cols-2">
                  <Form.Item label="用户名" name="username" required><Input autoComplete="off" placeholder="请输入测试用户名" /></Form.Item>
                  <Form.Item label="密码" name="password" required><Input.Password autoComplete="new-password" placeholder="请输入测试密码" /></Form.Item>
                </div>
              )}
              <div className="mt-5 min-h-10 text-xs leading-5 text-[var(--color-text-3)]">
                {mode === 'vault' ? '从下拉选择已有凭据，或在下拉底部新增并选用。端口和库名由本任务填写。' : '本次手动填写，不会保存到凭据管理。切回已有凭据会保留原来的选择。'}
              </div>
            </Form>
            <footer className="flex items-center justify-between gap-3 border-t border-[var(--color-border)] px-6 py-4">
              <span className="text-xs text-[var(--color-text-3)]">正式采集页面保持原样</span>
              <Button type="primary" onClick={() => {
                if (mode === 'vault' && !selected) { void notice.warning('请先选择凭据'); return; }
                if (mode === 'inline' && (!form.getFieldValue('username') || !form.getFieldValue('password'))) {
                  void notice.warning('请填写测试用户名和密码'); return;
                }
                void notice.success(mode === 'vault' ? `当前选择：${options.find((item) => item.value === selected)?.label}` : '当前使用手动录入的测试凭据');
              }}>确认选择（体验）</Button>
            </footer>
          </section>
        </div>
      </main>
      <Modal title="新增凭据" open={createOpen} onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        onOk={() => void saveCredential()} okText="保存并选用" cancelText="取消" destroyOnHidden>
        <div className="py-3">
          <CredentialQuickCreateForm form={createForm} types={[sqlType]} groups={[{ id: 1, name: 'Default' }]}
            lockedCategory lockedType />
        </div>
      </Modal>
      <Drawer title="系统管理 · 凭据管理（体验）" open={manageOpen} onClose={() => setManageOpen(false)} width={560}>
        <p className="mb-4 text-sm text-[var(--color-text-3)]">这里展示体验列表，新增后可立即回到采集表单选用。</p>
        <div className="mb-4 flex justify-end"><Button type="primary" onClick={openCreate}>新增凭据</Button></div>
        <div className="divide-y divide-[var(--color-border)]">
          {options.map((item) => (
            <div key={item.value} className="flex items-center justify-between gap-4 py-4">
              <div className="min-w-0"><div className="truncate font-medium">{item.label}</div><div className="mt-1 text-xs text-[var(--color-text-3)]">数据库 · 用户名密码 · Default</div></div>
              <Button onClick={() => { setSelected(item.value); setMode('vault'); setManageOpen(false); }}>选用</Button>
            </div>
          ))}
        </div>
      </Drawer>
    </ConfigProvider>
  );
}

const meta: Meta<typeof CredentialTrial> = {
  title: 'CMDB/配置采集/凭据选择体验', component: CredentialTrial,
  parameters: { layout: 'fullscreen' },
  decorators: [(Story) => <IntlProvider locale="zh" messages={messages}><Story /></IntlProvider>],
};
export default meta;
type Story = StoryObj<typeof CredentialTrial>;
export const Interactive: Story = { name: '先体验，不替换' };
