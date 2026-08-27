'use client';

/**
 * Skill 设置 After — 技能包选中后填声明变量；工具选中后填连接配置。
 */

import { useState, type ReactNode } from 'react';
import { Button, Form, Input, InputNumber, Select, Slider, Switch } from 'antd';
import { CloseOutlined, PlusOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { afterPanel } from './opspilot-after-system';
import { OpsPilotConversationDemo } from './opspilot-conversation';

const { TextArea } = Input;

function SkillFormSection({ title, extra, children }: { title: string; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-[var(--color-fill-2)] first:border-t-0">
      <div className={`${afterPanel.head} ${extra ? 'justify-between gap-2' : ''}`}>
        <div className="min-w-0 flex-1">{title}</div>
        {extra ? <div className="flex shrink-0 items-center">{extra}</div> : null}
      </div>
      <div className="px-3.5 py-1">{children}</div>
    </section>
  );
}

function SkillSettingRow({
  title,
  description,
  extra,
  children,
}: {
  title: string;
  description?: string;
  extra?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="border-b border-[var(--color-fill-2)] py-3 last:border-b-0">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[13px] font-medium leading-5 text-[var(--color-text-1)]">{title}</div>
          {description ? (
            <p className="mb-0 mt-0.5 max-w-[36ch] text-xs leading-5 text-[var(--color-text-3)]">{description}</p>
          ) : null}
        </div>
        {extra ? <div className="flex shrink-0 items-center gap-2 pt-0.5">{extra}</div> : null}
      </div>
      {children ? <div className="mt-2.5">{children}</div> : null}
    </div>
  );
}

function AddAction({ label }: { label: string }) {
  return (
    <Button type="text" size="small" icon={<PlusOutlined />} className="px-1.5 text-[var(--color-primary)]">
      {label}
    </Button>
  );
}

interface AttachField { key: string; value: string; secret?: boolean; required?: boolean }

interface AttachItem {
  id: string;
  name: string;
  icon: string;
  fields: AttachField[];
  missing?: number;
}

function AttachConfigList({
  items,
  openId,
  onToggle,
  actionLabel,
}: {
  items: AttachItem[];
  openId: string;
  onToggle: (id: string) => void;
  actionLabel: string;
}) {
  return (
    <div className="grid gap-2">
      {items.map((item) => {
        const open = openId === item.id;
        return (
          <div key={item.id} className="overflow-hidden rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)]">
            <div className="flex items-center justify-between gap-2 px-2.5 py-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[var(--color-fill-1)]">
                  <Icon type={item.icon} className="text-base" />
                </span>
                <span className="truncate text-[13px] font-medium text-[var(--color-text-1)]">{item.name}</span>
                {!open ? (
                  item.missing ? (
                    <span className="shrink-0 text-[11px] text-[var(--color-warning)]">缺 {item.missing} 项必填</span>
                  ) : (
                    <span className="shrink-0 text-[11px] text-[var(--color-success)]">已配置</span>
                  )
                ) : null}
              </div>
              <div className="flex shrink-0 items-center">
                <Button type="link" size="small" className="h-auto px-1" onClick={() => onToggle(item.id)}>
                  {open ? '收起' : actionLabel}
                </Button>
                <button
                  type="button"
                  className="inline-flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-4)] hover:bg-[var(--color-fill-1)] hover:text-[var(--color-text-2)]"
                  aria-label={`移除 ${item.name}`}
                >
                  <CloseOutlined className="text-[10px]" />
                </button>
              </div>
            </div>
            {open ? (
              <div className="grid gap-2 border-t border-[var(--color-fill-2)] bg-[var(--color-fill-1)] px-2.5 py-2.5">
                {item.fields.map((field) => (
                  <div key={field.key} className="grid grid-cols-[88px_minmax(0,1fr)] items-center gap-2">
                    <span className="truncate font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[11px] text-[var(--color-text-3)]">
                      {field.key}
                    </span>
                    {field.secret ? (
                      <Input.Password size="small" defaultValue={field.value} />
                    ) : (
                      <Input
                        size="small"
                        defaultValue={field.value}
                        placeholder={field.required && !field.value ? '必填' : undefined}
                      />
                    )}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

const SKILL_PACKS: AttachItem[] = [
  {
    id: 'k8s',
    name: 'K8s 变更诊断',
    icon: 'jinengpeixun',
    fields: [
      { key: 'cluster_env', value: 'prod-hz' },
      { key: 'risk_window', value: '22:00-06:00' },
      { key: 'kubeconfig', value: 'k8s-token', secret: true },
    ],
  },
  {
    id: 'duty',
    name: '值班手册',
    icon: 'jinengpeixun',
    missing: 1,
    fields: [
      { key: 'oncall_group', value: 'SRE-A' },
      { key: 'escalation', value: '', required: true },
    ],
  },
];

const SKILL_TOOLS: AttachItem[] = [
  {
    id: 'k8s',
    name: 'Kubernetes',
    icon: 'gongjuxiang',
    fields: [
      { key: 'cluster', value: 'prod-hz' },
      { key: 'namespace', value: 'default' },
      { key: 'token', value: 'k8s-token', secret: true },
    ],
  },
  {
    id: 'prom',
    name: 'Prometheus 查询',
    icon: 'gongjuji',
    fields: [
      { key: 'query', value: 'up{job="nginx"}' },
      { key: 'step', value: '15s' },
    ],
  },
  {
    id: 'approve',
    name: '变更审批',
    icon: 'shezhi',
    fields: [{ key: 'approver', value: 'sre-oncall' }],
  },
];

function SkillConfigColumn() {
  const labelCol = { flex: '0 0 96px' as const };
  const [openPackId, setOpenPackId] = useState('k8s');
  const [openToolId, setOpenToolId] = useState('');

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto pr-0.5">
        <SkillFormSection title="基本信息">
          <Form
            layout="horizontal"
            labelCol={labelCol}
            wrapperCol={{ flex: 1 }}
            colon={false}
            className="[&_.ant-form-item]:mb-3 [&_.ant-form-item-label]:pr-3"
          >
            <Form.Item label="名称" required>
              <Input defaultValue="Kubernetes Diagnosis" />
            </Form.Item>
            <Form.Item label="管理组织" required>
              <Select mode="multiple" defaultValue={['SRE']} options={[{ value: 'SRE', label: 'SRE' }]} />
            </Form.Item>
            <Form.Item label="使用组织" required tooltip="管理组织会自动并入，且不可从使用组织中删除。">
              <Select
                mode="multiple"
                defaultValue={['SRE', '平台运维']}
                options={[
                  { value: 'SRE', label: 'SRE' },
                  { value: '平台运维', label: '平台运维' },
                ]}
              />
            </Form.Item>
            <Form.Item label="简介" required>
              <TextArea rows={3} defaultValue="面向 K8s 工作负载的故障定位、变更建议与回滚辅助。" />
            </Form.Item>
            <Form.Item label="LLM 模型" required>
              <Select
                defaultValue="gpt-4o"
                options={[
                  { value: 'gpt-4o', label: 'gpt-4o · OpenAI' },
                  { value: 'deepseek-v3', label: 'deepseek-v3 · DeepSeek' },
                ]}
              />
            </Form.Item>
            <Form.Item label="知识库">
              <Select
                mode="multiple"
                defaultValue={['SRE Playbooks']}
                options={[{ value: 'SRE Playbooks', label: 'SRE Playbooks' }]}
              />
            </Form.Item>
          </Form>

          <div className="-mx-3.5 border-y border-[var(--color-fill-2)] px-3.5">
            <SkillSettingRow title="展示思考" description="回复中保留推理过程，默认可折叠。" extra={<Switch defaultChecked size="small" />} />
            <SkillSettingRow title="问题建议" description="回答后给出可执行的下一步。" extra={<Switch defaultChecked size="small" />} />
            <SkillSettingRow title="问题优化" description="先改写提问再检索，适合含糊问题。" extra={<Switch size="small" />} />
          </div>

          <Form
            layout="horizontal"
            labelCol={labelCol}
            wrapperCol={{ flex: 1 }}
            colon={false}
            className="pt-3 [&_.ant-form-item]:mb-3 [&_.ant-form-item-label]:pr-3"
          >
            <Form.Item label="温度">
              <div className="flex items-center gap-3">
                <Slider min={0} max={1} step={0.01} defaultValue={0.7} className="m-0 flex-1" />
                <InputNumber min={0} max={1} step={0.01} defaultValue={0.7} className="w-[72px]" />
              </div>
            </Form.Item>
            <Form.Item label="提示" required>
              <TextArea
                rows={4}
                defaultValue={'你是运维助手。先确认风险再执行；补丁必须可回滚。\n当前角色：{{role}}'}
              />
            </Form.Item>
            <Form.Item label="提示词参数">
              <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_88px] gap-2">
                <Input defaultValue="role" disabled />
                <Input defaultValue="SRE 值班工程师" />
                <Select defaultValue="text" options={[{ value: 'text', label: '文本' }, { value: 'password', label: '密码' }]} />
              </div>
            </Form.Item>
            <Form.Item label="引导语" className="mb-1">
              <TextArea
                rows={3}
                defaultValue={'您好，请问有什么可以帮助您的吗？\n[nginx 探针缺失怎么修？]\n[如何安全回滚 deployment？]'}
              />
            </Form.Item>
          </Form>
        </SkillFormSection>

        <SkillFormSection title="聊天增强">
          <SkillSettingRow
            title="聊天历史"
            description="保留用户与智能体最近若干轮对话。"
            extra={
              <>
                <InputNumber min={1} max={100} defaultValue={10} size="small" className="w-16" />
                <span className="text-xs text-[var(--color-text-3)]">轮</span>
                <Switch defaultChecked size="small" />
              </>
            }
          />

          <SkillSettingRow title="技能包" extra={<AddAction label="选择" />}>
            <AttachConfigList
              items={SKILL_PACKS}
              openId={openPackId}
              onToggle={(id) => setOpenPackId((prev) => (prev === id ? '' : id))}
              actionLabel="变量"
            />
          </SkillSettingRow>

          <SkillSettingRow
            title="工具"
            extra={
              <>
                <AddAction label="选择" />
                <Switch defaultChecked size="small" />
              </>
            }
          >
            <AttachConfigList
              items={SKILL_TOOLS}
              openId={openToolId}
              onToggle={(id) => setOpenToolId((prev) => (prev === id ? '' : id))}
              actionLabel="配置"
            />
          </SkillSettingRow>
        </SkillFormSection>
      </div>

      <div className="shrink-0 border-t border-[var(--color-fill-2)] px-3.5 py-2.5">
        <Button type="primary">保存</Button>
      </div>
    </div>
  );
}

export function PageSkillSettings() {
  return (
    <div className="flex h-full min-h-[560px]">
      <div className="flex w-1/2 min-w-0 flex-col border-r border-[var(--color-fill-2)]">
        <SkillConfigColumn />
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className={`${afterPanel.head} justify-between gap-2`}>
          <div>
            <div>试运行</div>
            <div className="text-xs font-normal text-[var(--color-text-3)]">用当前配置预览，不写入线上技能</div>
          </div>
          <span className="rounded-md bg-[var(--color-fill-1)] px-1.5 py-0.5 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[11px] text-[var(--color-text-3)]">
            gpt-4o
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-3">
          <OpsPilotConversationDemo />
        </div>
      </div>
    </div>
  );
}
