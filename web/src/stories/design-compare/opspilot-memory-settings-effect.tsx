'use client';

/**
 * Memory / Settings After — 对齐生产字段与分区，不另起视觉语言。
 */

import { useState } from 'react';
import { Button, Form, Input, Select, Table } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { afterPanel } from './opspilot-after-system';

const { TextArea } = Input;

const label = 'text-[13px] font-semibold text-[var(--color-text-2)]';
const hint = 'mt-1.5 text-[11px] leading-relaxed text-[var(--color-text-3)]';

const MEMORIES = [
  {
    id: 12,
    owner: 'qiu',
    updatedAt: '2026-08-24 14:12',
    content: `# nginx 探针约定\n\n- readinessProbe 必须配置\n- 超时 3s，失败阈值 3\n- 变更窗口：周五 22:00–06:00`,
  },
  {
    id: 18,
    owner: 'sre-bot',
    updatedAt: '2026-08-22 09:40',
    content: `# 回滚联系人\n\n生产回滚先找值班 SRE，再通知变更审批人。冻结期不发版。`,
  },
  {
    id: 21,
    owner: 'qiu',
    updatedAt: '2026-08-19 21:06',
    content: `# 生产冻结期\n\n大促前 48h 禁止非紧急变更；紧急变更走审批工具。`,
  },
];

function summaryOf(content: string) {
  const line = content.replace(/^#+\s*/, '').split('\n').find((item) => item.trim());
  return `${(line || '').slice(0, 36)}…`;
}

function MemoryPreview({ content }: { content: string }) {
  const [title, ...rest] = content.split('\n');
  return (
    <div className="text-[13px] leading-relaxed text-[var(--color-text-2)]">
      <h3 className="mb-2 mt-0 text-[15px] font-semibold text-[var(--color-text-1)]">{title.replace(/^#+\s*/, '')}</h3>
      {rest
        .filter((line) => line.trim())
        .map((line) => (
          <p key={line} className="mb-1.5 mt-0">
            {line}
          </p>
        ))}
    </div>
  );
}

export function MemoryMemoriesWorkbench() {
  const [selectedId, setSelectedId] = useState(12);
  const [editing, setEditing] = useState(false);
  const selected = MEMORIES.find((item) => item.id === selectedId) ?? MEMORIES[0];

  return (
    <div className="flex h-full min-h-0">
      <section className="flex min-h-0 min-w-0 flex-[6] flex-col border-r border-[var(--color-fill-2)]">
        <div className={`${afterPanel.head} justify-between gap-2`}>
          <span>记忆列表</span>
          <Select
            allowClear
            placeholder="筛选用户"
            className="w-[140px]"
            size="small"
            options={[
              { value: 'qiu', label: 'qiu' },
              { value: 'sre-bot', label: 'sre-bot' },
            ]}
          />
        </div>
        <Table
          size="small"
          pagination={false}
          rowKey="id"
          dataSource={MEMORIES}
          onRow={(record) => ({
            onClick: () => {
              setSelectedId(record.id);
              setEditing(false);
            },
          })}
          rowClassName={(record) =>
            record.id === selectedId
              ? 'cursor-pointer bg-[var(--color-primary-bg-active)] [&_td]:bg-[var(--color-primary-bg-active)]'
              : 'cursor-pointer'
          }
          className="[&_.ant-table]:bg-transparent [&_.ant-table-thead>tr>th]:bg-transparent [&_.ant-table-thead>tr>th]:text-[12px] [&_.ant-table-thead>tr>th]:text-[var(--color-text-3)] [&_.ant-table-tbody>tr>td]:text-[13px] [&_.ant-table-tbody>tr>td]:text-[var(--color-text-2)]"
          columns={[
            { title: '用户', dataIndex: 'owner', width: 88, ellipsis: true },
            { title: '记忆 ID', dataIndex: 'id', width: 80, render: (id: number) => `m-${id}` },
            { title: '更新时间', dataIndex: 'updatedAt', width: 136 },
            {
              title: '摘要',
              key: 'summary',
              ellipsis: true,
              render: (_, record) => (
                <span className="text-[var(--color-primary)]">{summaryOf(record.content)}</span>
              ),
            },
            {
              title: '操作',
              width: 108,
              render: (_, record) => (
                <div className="flex gap-2">
                  <Button
                    type="link"
                    className="h-auto p-0 text-[12px]"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedId(record.id);
                      setEditing(false);
                    }}
                  >
                    查看
                  </Button>
                  <Button type="link" danger className="h-auto p-0 text-[12px]" onClick={(event) => event.stopPropagation()}>
                    删除
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </section>

      <aside className="flex min-h-0 min-w-0 flex-[4] flex-col">
        <div className={`${afterPanel.head} justify-between gap-2`}>
          <span>记忆</span>
          {editing ? (
            <div className="flex gap-2">
              <Button type="link" className="h-7 px-2 text-[12px] text-[var(--color-text-3)]" onClick={() => setEditing(false)}>
                取消
              </Button>
              <Button type="primary" className="h-7 px-3 text-[12px]" onClick={() => setEditing(false)}>
                保存
              </Button>
            </div>
          ) : (
            <Button type="link" className="h-7 px-2 text-[12px]" onClick={() => setEditing(true)}>
              编辑
            </Button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
          {editing ? (
            <TextArea className="h-full min-h-[360px] font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[13px]" defaultValue={selected.content} />
          ) : (
            <MemoryPreview content={selected.content} />
          )}
        </div>
      </aside>
    </div>
  );
}

export function MemoryConfigWorkbench() {
  const [tested, setTested] = useState(false);

  return (
    <div className="flex h-full min-h-[560px]">
      <div className="flex min-w-0 flex-[6] flex-col border-r border-[var(--color-fill-2)]">
        <section>
          <div className={afterPanel.head}>基本信息</div>
          <Form layout="horizontal" colon={false} className="px-3.5 py-3.5 [&_.ant-form-item]:mb-3">
            <Form.Item label="名称" required labelCol={{ style: { width: 92 } }} wrapperCol={{ flex: 1 }}>
              <Input defaultValue="Prod Ops Memory" />
            </Form.Item>
            <Form.Item label="记忆类型" required labelCol={{ style: { width: 92 } }} wrapperCol={{ flex: 1 }}>
              <Select disabled defaultValue="team" options={[{ value: 'personal', label: '个人记忆' }, { value: 'team', label: '组织记忆' }]} />
            </Form.Item>
            <Form.Item label="管理组织" required labelCol={{ style: { width: 92 } }} wrapperCol={{ flex: 1 }}>
              <Select mode="multiple" defaultValue={['SRE']} options={[{ value: 'SRE', label: 'SRE' }, { value: '平台运维', label: '平台运维' }]} />
            </Form.Item>
            <Form.Item label="简介" labelCol={{ style: { width: 92 } }} wrapperCol={{ flex: 1 }} className="mb-0">
              <TextArea rows={3} defaultValue="沉淀生产变更窗口、探针约定与回滚联系人。" />
            </Form.Item>
          </Form>
        </section>

        <section className="flex min-h-0 flex-1 flex-col border-t border-[var(--color-fill-2)]">
          <div className={afterPanel.head}>记忆写入规则</div>
          <div className="flex min-h-0 flex-1 flex-col gap-3 p-3.5">
            <div className="flex min-h-0 flex-1 flex-col">
              <div className={label}>写入规则</div>
              <p className={`${hint} mb-2 mt-0`}>记忆准则定义“什么内容值得写”和“记忆应如何组织”。</p>
              <TextArea
                className="min-h-[120px] flex-1"
                defaultValue="仅记录可复用的运维事实：故障对象、根因、处置与结论。排除临时排障碎语。"
              />
            </div>
            <div>
              <div className={label}>默认模型</div>
              <p className={`${hint} mb-2 mt-0`}>用于记忆提炼、结构判断和合并更新。</p>
              <Select defaultValue="gpt-4o" options={[{ value: 'gpt-4o', label: 'gpt-4o' }, { value: 'deepseek-v3', label: 'deepseek-v3' }]} />
            </div>
          </div>
        </section>

        <div className="shrink-0 border-t border-[var(--color-fill-2)] px-3.5 py-2.5">
          <Button type="primary" className="h-8 px-3 text-xs font-semibold">
            保存
          </Button>
        </div>
      </div>

      <div className="flex min-w-0 flex-[4] flex-col">
        <section>
          <div className={afterPanel.head}>记忆写入测试</div>
          <div className="flex flex-col gap-3 p-3.5">
            <div>
              <div className={`${label} mb-2`}>输入内容</div>
              <p className={`${hint} mb-2 mt-0`}>输入 workflow 运行后希望沉淀到记忆里的内容，测试记忆如何提炼、归纳和更新。</p>
              <TextArea
                rows={5}
                defaultValue="nginx-web 近 24h 重启 11 次；无探针窗口 5xx 明显高于基线。建议补 readinessProbe。"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[13px] text-[var(--color-text-2)]">引用已有记忆</span>
              <Select
                allowClear
                className="w-48"
                placeholder="不引用"
                options={MEMORIES.map((item) => ({ value: item.id, label: `${item.owner} / ${item.id}` }))}
              />
              <Button type="primary" className="ml-auto h-8 px-3 text-xs font-semibold" onClick={() => setTested(true)}>
                测试
              </Button>
            </div>
          </div>
        </section>

        <section className="flex min-h-0 flex-1 flex-col border-t border-[var(--color-fill-2)]">
          <div className={afterPanel.head}>测试结果</div>
          <div className="flex min-h-0 flex-1 flex-col p-3.5">
            {tested ? (
              <div className="flex-1 overflow-auto whitespace-pre-wrap rounded-md bg-[var(--color-fill-1)] p-3 font-[ui-monospace,SFMono-Regular,Menlo,monospace] text-[13px] leading-relaxed">
                {`# nginx 探针约定\n\n- 近 24h 重启 11 次，5xx 高于基线\n- 建议补 readinessProbe：超时 3s / 失败阈值 3`}
              </div>
            ) : (
              <div className="flex flex-1 flex-col items-center justify-center rounded-md bg-[var(--color-fill-1)] p-6">
                <div className="mb-1 text-[13px] font-medium text-[var(--color-text-2)]">等待测试结果</div>
                <div className={hint}>当前未引用已有记忆。点击「测试」后，这里会展示新建记忆效果。</div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function QuotaUsageBlock() {
  const rows = [
    { label: '智能体（统一配额）', usage: 6, total: 20 },
    { label: '机器人（共享配额）', usage: 3, total: 10 },
  ];

  return (
    <div>
      <div className="mb-4 flex h-20 items-center rounded-md bg-[var(--color-bg)] p-4">
        <div>
          <h2 className="mb-2 text-base font-semibold text-[var(--color-text-1)]">我的配额</h2>
          <p className="mb-0 text-xs text-[var(--color-text-3)]">显示我的总配额使用量。当配额不足时，请联系管理员申请增加。</p>
        </div>
      </div>
      <section className="rounded-md bg-[var(--color-bg)] p-4">
        <h2 className="mb-4 text-[15px] font-semibold text-[var(--color-text-1)]">配额使用量</h2>
        {rows.map((row) => {
          const percent = Math.min(100, (row.usage / row.total) * 100);
          return (
            <div key={row.label} className="mb-4 flex items-center gap-4">
              <div className="flex w-1/3 items-center justify-between text-sm">
                <span className="text-[var(--color-text-1)]">{row.label}</span>
                <span className="text-[var(--color-text-3)]">
                  {row.usage}/{row.total}
                </span>
              </div>
              <div className="h-2.5 flex-1 overflow-hidden rounded-md bg-[var(--color-fill-2)]">
                <div className="h-full rounded-md bg-[var(--color-success)]" style={{ width: `${percent}%` }} />
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}

export function SettingsQuotaWorkbench() {
  return <QuotaUsageBlock />;
}

export function SettingsManageWorkbench() {
  return (
    <div>
      <div className="mb-4 flex h-20 items-center rounded-md bg-[var(--color-bg)] p-4">
        <div>
          <h2 className="mb-2 text-base font-semibold text-[var(--color-text-1)]">管理配额</h2>
          <p className="mb-0 text-xs text-[var(--color-text-3)]">管理员可以为不同角色设置不同的配额。</p>
        </div>
      </div>
      <div className="rounded-md bg-[var(--color-bg)] p-4">
        <div className="mb-4 flex justify-end gap-2">
          <Input.Search placeholder="搜索..." enterButton={<SearchOutlined />} className="w-60" />
          <Button type="primary">+ 添加</Button>
        </div>
        <Table
          size="middle"
          pagination={{ pageSize: 10, current: 1, total: 3 }}
          rowKey="id"
          dataSource={[
            { id: 1, name: 'SRE 统一配额', skill: 20, bot: 8 },
            { id: 2, name: '平台共享配额', skill: 12, bot: 4 },
            { id: 3, name: '值班机器人配额', skill: 6, bot: 10 },
          ]}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: '智能体', dataIndex: 'skill', width: 120 },
            { title: '机器人', dataIndex: 'bot', width: 120 },
            {
              title: '操作',
              width: 140,
              render: () => (
                <>
                  <Button type="link" className="mr-2 px-0">
                    编辑
                  </Button>
                  <Button type="link" danger className="px-0">
                    删除
                  </Button>
                </>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
