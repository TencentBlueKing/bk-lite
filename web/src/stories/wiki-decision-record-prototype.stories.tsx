'use client';

import { useMemo, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { SwapOutlined } from '@ant-design/icons';
import { Button, ConfigProvider, Tag } from 'antd';

type DecisionKind = 'knowledge_conflict' | 'page_identity';
type DecisionView = 'pending' | 'history';
type RuleStatus = 'active' | 'revoked';

interface KnowledgeSnapshot {
  label: string;
  title: string;
  version: string;
  source: string;
  type: string;
  description: string;
  evidence: string;
  sourceCount: number;
  relationCount: number;
}

interface DecisionItem {
  id: string;
  kind: DecisionKind;
  title: string;
  summary: string;
  reason: string;
  trigger: string;
  impact: string;
  recoverability: string;
  time: string;
  current: KnowledgeSnapshot;
  incoming: KnowledgeSnapshot;
  result?: string;
  operator?: string;
  handledAt?: string;
  ruleStatus?: RuleStatus;
  replayCount?: number;
  lastReplay?: string;
  revokedReason?: string;
}

const pendingItems: DecisionItem[] = [
  {
    id: 'pending-k8s',
    kind: 'knowledge_conflict',
    title: 'Kubernetes 节点磁盘告警阈值',
    summary: '新资料将告警阈值从 80% 调整为 85%，与当前知识不一致',
    reason: '关键结论发生变化',
    trigger: 'SRE 运行标准 v2026.06',
    impact: '1 个页面 · 3 条关系 · 8 个分块',
    recoverability: '旧版本保留，可随时恢复',
    time: '10 分钟前',
    current: {
      label: '当前知识',
      title: 'Kubernetes 节点磁盘告警阈值',
      version: '当前 v12',
      source: 'Kubernetes 运维手册 v2025.12',
      type: '运维规则',
      description: '节点磁盘使用率达到阈值，并连续 3 次采集超过阈值时触发。',
      evidence: '节点磁盘使用率达到 80% 时触发告警。',
      sourceCount: 3,
      relationCount: 3,
    },
    incoming: {
      label: '新知识',
      title: 'Kubernetes 节点磁盘告警阈值',
      version: '候选 v13',
      source: 'SRE 运行标准 v2026.06',
      type: '运维规则',
      description: '节点磁盘使用率达到阈值，并持续 5 分钟超过阈值时触发。',
      evidence: '节点磁盘使用率达到 85% 时触发告警。',
      sourceCount: 2,
      relationCount: 3,
    },
  },
  {
    id: 'pending-cmdb',
    kind: 'page_identity',
    title: '“CMDB”与“配置平台”可能是同一知识',
    summary: '标题别名、页面类型与核心内容高度一致，需要确认知识边界',
    reason: '系统无法确认两个知识是否指向同一对象',
    trigger: '资产管理规范、产品能力介绍',
    impact: '2 个页面 · 5 条关系 · 4 份证据',
    recoverability: '来源页面归档，可随时恢复',
    time: '昨天 16:42',
    current: {
      label: '当前知识',
      title: '配置平台',
      version: '当前知识',
      source: '资产管理规范',
      type: '实体 · 人工维护',
      description: '统一管理业务、主机、服务实例与模型关系，是资产数据的主要事实来源。',
      evidence: '3 份资料证据 · 4 条页面关系',
      sourceCount: 3,
      relationCount: 4,
    },
    incoming: {
      label: '新知识',
      title: 'CMDB',
      version: '待确认',
      source: '产品能力介绍',
      type: '实体 · AI 生成',
      description: '配置管理数据库，用于记录基础设施资源、属性以及资源之间的关联。',
      evidence: '1 份资料证据 · 2 条页面关系',
      sourceCount: 1,
      relationCount: 2,
    },
  },
];

const historyItems: DecisionItem[] = [
  {
    ...pendingItems[0],
    id: 'history-k8s',
    time: '7 月 15 日 14:28',
    result: '使用新知识',
    operator: 'admin',
    handledAt: '2026-07-15 14:28',
    ruleStatus: 'active',
    replayCount: 4,
    lastReplay: '今天 09:16',
  },
  {
    ...pendingItems[1],
    id: 'history-cmdb',
    time: '7 月 13 日 16:42',
    result: '保持页面独立',
    operator: 'wiki-owner',
    handledAt: '2026-07-13 16:42',
    ruleStatus: 'revoked',
    replayCount: 2,
    lastReplay: '7 月 14 日 11:02',
    revokedReason: '资料边界发生变化，规则已停止自动复用',
  },
];

const colors = {
  ink: '#14213d',
  text: '#34415e',
  muted: '#73809f',
  border: '#e3e9f5',
  indigo: '#5146e5',
  indigoSoft: '#f2f3ff',
  blueSoft: '#eef4ff',
  amber: '#d38a12',
  amberSoft: '#fff9eb',
  green: '#1c9b61',
  greenSoft: '#ecfbf4',
  canvas: '#f4f7ff',
};

const cardShadow = '0 10px 30px rgba(68, 88, 145, 0.08)';

function KindTag({ kind }: { kind: DecisionKind }) {
  const isConflict = kind === 'knowledge_conflict';
  return (
    <Tag
      bordered={false}
      style={{
        margin: 0,
        color: isConflict ? '#b76800' : '#3f48cf',
        background: isConflict ? '#fff6dc' : '#eef0ff',
        borderRadius: 6,
        fontSize: 12,
        lineHeight: '22px',
      }}
    >
      {isConflict ? '知识更新冲突' : '页面合并决策'}
    </Tag>
  );
}

function InfoCell({ label, value, tone = 'indigo' }: { label: string; value: string; tone?: 'indigo' | 'green' }) {
  return (
    <div style={{ padding: '14px 16px', minWidth: 0 }}>
      <div style={{ color: tone === 'green' ? colors.green : '#6f72d8', fontSize: 12, marginBottom: 6 }}>{label}</div>
      <div style={{ color: colors.ink, fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</div>
    </div>
  );
}

function KnowledgeCard({ snapshot, side }: { snapshot: KnowledgeSnapshot; side: 'current' | 'incoming' }) {
  const isCurrent = side === 'current';
  return (
    <section
      style={{
        flex: 1,
        minWidth: 0,
        border: '1px solid ' + (isCurrent ? '#f0dfb7' : '#dfe2ff'),
        borderTop: '3px solid ' + (isCurrent ? '#e4a53d' : '#6963ee'),
        borderRadius: 14,
        background: isCurrent ? '#fffdf7' : '#fafaff',
        overflow: 'hidden',
      }}
    >
      <div style={{ padding: '13px 16px', borderBottom: '1px solid ' + (isCurrent ? '#f4ead2' : '#e7e8fa'), display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <div style={{ color: colors.muted, fontSize: 12, marginBottom: 4 }}>{snapshot.label}</div>
          <div style={{ color: colors.ink, fontSize: 16, lineHeight: 1.35, fontWeight: 700 }}>{snapshot.title}</div>
        </div>
        <Tag style={{ margin: 0, color: isCurrent ? '#9a6708' : '#5146e5', borderColor: isCurrent ? '#e8ce95' : '#cdd0ff', background: isCurrent ? '#fff8e6' : '#f0f1ff' }}>{snapshot.version}</Tag>
      </div>

      <div style={{ padding: '13px 16px 15px' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14 }}>
          <span style={{ padding: '4px 9px', borderRadius: 999, color: isCurrent ? '#8f6b25' : '#5960bd', background: isCurrent ? '#fff5d9' : '#eef0ff', fontSize: 12 }}>{snapshot.source}</span>
          <span style={{ color: colors.muted, fontSize: 12 }}>{snapshot.type}</span>
        </div>
        <div style={{ color: colors.ink, fontSize: 14, fontWeight: 700, marginBottom: 8 }}>知识内容</div>
        <p style={{ margin: '0 0 12px', color: colors.text, fontSize: 14, lineHeight: 1.7 }}>{snapshot.description}</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '11px 13px', borderRadius: 9, background: isCurrent ? '#fff3ef' : '#ecfaf2', color: colors.text, fontSize: 14 }}>
          <span style={{ color: isCurrent ? '#d34c3f' : '#22a563', fontWeight: 700 }}>{isCurrent ? '−' : '+'}</span>
          <span>{snapshot.evidence}</span>
        </div>
        <div style={{ display: 'flex', gap: 20, marginTop: 13, color: colors.muted, fontSize: 12 }}>
          <span>{snapshot.sourceCount} 份资料证据</span>
          <span>{snapshot.relationCount} 条知识关系</span>
        </div>
      </div>
    </section>
  );
}

function DecisionList({ items, selectedId, onSelect, view }: { items: DecisionItem[]; selectedId: string; onSelect: (id: string) => void; view: DecisionView }) {
  return (
    <aside style={{ width: 330, borderRight: '1px solid ' + colors.border, padding: '14px 12px', background: '#fbfcff', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1px 5px 12px' }}>
        <span style={{ color: colors.ink, fontSize: 13, fontWeight: 700 }}>{view === 'pending' ? '需要你判断' : '最近处理'}</span>
        <span style={{ color: colors.muted, fontSize: 12 }}>共 {items.length} 项</span>
      </div>
      <div style={{ display: 'grid', gap: 9 }}>
        {items.map((item) => {
          const selected = item.id === selectedId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              style={{
                width: '100%',
                textAlign: 'left',
                border: '1px solid ' + (selected ? '#cbd8ff' : colors.border),
                borderRadius: 12,
                background: selected ? '#edf3ff' : '#ffffff',
                boxShadow: selected ? '0 8px 22px rgba(83, 105, 180, 0.10)' : 'none',
                padding: '12px 13px',
                cursor: 'pointer',
                fontFamily: 'inherit',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginBottom: 9 }}>
                <KindTag kind={item.kind} />
                <span style={{ color: colors.muted, fontSize: 12, whiteSpace: 'nowrap' }}>{item.time}</span>
              </div>
              <div style={{ color: colors.ink, fontSize: 14, fontWeight: 700, lineHeight: 1.45, marginBottom: 5 }}>{item.title}</div>
              <div style={{ color: colors.muted, fontSize: 12, lineHeight: 1.55, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{item.summary}</div>
              {view === 'history' && item.result ? (
                <div style={{ marginTop: 10, color: item.ruleStatus === 'active' ? colors.green : '#6e7690', fontSize: 12, fontWeight: 600 }}>
                  {item.result} · {item.ruleStatus === 'active' ? '规则生效中' : '规则已失效'}
                </div>
              ) : null}
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function HistorySummary({ item }: { item: DecisionItem }) {
  const active = item.ruleStatus === 'active';
  return (
    <div style={{ margin: '0 20px 16px', border: '1px solid ' + (active ? '#cbeedc' : '#e3e7f1'), borderRadius: 12, background: active ? '#f2fcf7' : '#f8f9fc', padding: '13px 15px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 26, minWidth: 0 }}>
        <div>
          <div style={{ color: colors.muted, fontSize: 12, marginBottom: 4 }}>处理结果</div>
          <div style={{ color: active ? colors.green : colors.ink, fontSize: 15, fontWeight: 800 }}>{item.result}</div>
        </div>
        <div>
          <div style={{ color: colors.muted, fontSize: 12, marginBottom: 4 }}>处理人 / 时间</div>
          <div style={{ color: colors.text, fontSize: 13 }}>{item.operator} · {item.handledAt}</div>
        </div>
        <div>
          <div style={{ color: colors.muted, fontSize: 12, marginBottom: 4 }}>后续自动复用</div>
          <div style={{ color: colors.text, fontSize: 13 }}>{active ? '已复用 ' + item.replayCount + ' 次 · 最近 ' + item.lastReplay : '已停止 · 曾复用 ' + item.replayCount + ' 次'}</div>
        </div>
      </div>
      {active ? <Button danger>停止后续自动复用</Button> : <Tag style={{ margin: 0, color: '#6d758c', background: '#eef0f5', borderColor: '#dfe3ec' }}>规则已失效</Tag>}
    </div>
  );
}

function DecisionRecordPrototype({ initialView = 'pending' }: { initialView?: DecisionView }) {
  const [view, setView] = useState<DecisionView>(initialView);
  const items = view === 'pending' ? pendingItems : historyItems;
  const [pendingId, setPendingId] = useState(pendingItems[0].id);
  const [historyId, setHistoryId] = useState(historyItems[0].id);
  const selectedId = view === 'pending' ? pendingId : historyId;
  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? items[0], [items, selectedId]);

  const switchView = (next: DecisionView) => {
    setView(next);
  };

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: colors.indigo,
          borderRadius: 8,
          colorText: colors.ink,
          fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <main style={{ minHeight: '100vh', padding: 24, background: colors.canvas, color: colors.ink }}>
        <div style={{ height: 'calc(100vh - 48px)', minHeight: 700, maxWidth: 1510, margin: '0 auto', background: '#fff', border: '1px solid #e1e7f3', borderRadius: 16, overflow: 'hidden', boxShadow: cardShadow, display: 'flex', flexDirection: 'column' }}>
          <header style={{ height: 76, padding: '0 20px', borderBottom: '1px solid ' + colors.border, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                <h1 style={{ margin: 0, fontSize: 20, lineHeight: 1.2, color: colors.ink }}>{view === 'pending' ? '待决策' : '决策记录'}</h1>
                <span style={{ minWidth: 22, height: 22, padding: '0 6px', borderRadius: 6, background: colors.indigoSoft, color: colors.indigo, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700 }}>{items.length}</span>
              </div>
              <div style={{ color: colors.muted, fontSize: 12 }}>
                {view === 'pending' ? '只展示需要你选择知识结果的事项，结构维护已自动完成' : '查看人工决策及其后续自动复用情况'}
              </div>
            </div>
            <Button onClick={() => switchView(view === 'pending' ? 'history' : 'pending')}>
              {view === 'pending' ? '查看决策记录' : '返回待决策'}
            </Button>
          </header>

          <div style={{ minHeight: 0, flex: 1, display: 'flex' }}>
            <DecisionList
              items={items}
              selectedId={selectedId}
              view={view}
              onSelect={(id) => (view === 'pending' ? setPendingId(id) : setHistoryId(id))}
            />

            <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', background: '#fff' }}>
              <div style={{ padding: '15px 20px 13px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                    <KindTag kind={selected.kind} />
                    <Tag style={{ margin: 0, color: view === 'pending' ? colors.ink : colors.green, borderColor: view === 'pending' ? '#dce1eb' : '#bfe8d3', background: view === 'pending' ? '#fff' : colors.greenSoft }}>{view === 'pending' ? '待决策' : selected.result}</Tag>
                  </div>
                  <h2 style={{ margin: '0 0 7px', fontSize: 18, lineHeight: 1.35, color: colors.ink }}>{selected.title}</h2>
                  <p style={{ margin: 0, color: colors.text, fontSize: 13 }}>{selected.summary}</p>
                </div>
                <div style={{ color: colors.muted, fontSize: 12, whiteSpace: 'nowrap', paddingTop: 4 }}>{view === 'history' ? selected.handledAt : selected.time}</div>
              </div>

              <div style={{ margin: '0 20px 14px', border: '1px solid ' + colors.border, borderRadius: 12, background: '#fbfcff', display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', boxShadow: '0 4px 14px rgba(74, 91, 142, 0.04)' }}>
                <InfoCell label="为什么需要决策" value={selected.reason} />
                <InfoCell label="触发来源" value={selected.trigger} />
                <InfoCell label="影响范围" value={selected.impact} />
                <InfoCell label="可恢复性" value={selected.recoverability} tone="green" />
              </div>

              {view === 'history' ? <HistorySummary item={selected} /> : null}

              <div style={{ minHeight: 0, flex: 1, overflowY: 'auto', padding: '0 20px 18px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
                  <div style={{ color: colors.ink, fontSize: 14, fontWeight: 800 }}>{view === 'pending' ? '比较知识差异' : '决策时的知识快照'}</div>
                  <div style={{ color: colors.muted, fontSize: 12 }}>{selected.kind === 'knowledge_conflict' ? '仅突出发生变化的结论' : '确认两个知识是否表达同一对象'}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'stretch', gap: 14 }}>
                  <KnowledgeCard snapshot={selected.current} side="current" />
                  <div style={{ width: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <span style={{ width: 40, height: 40, borderRadius: '50%', border: '1px solid #dfe2ff', color: colors.indigo, background: '#f1f2ff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>
                      <SwapOutlined />
                    </span>
                  </div>
                  <KnowledgeCard snapshot={selected.incoming} side="incoming" />
                </div>
                {view === 'history' && selected.revokedReason ? (
                  <div style={{ marginTop: 12, padding: '10px 13px', borderRadius: 9, background: '#fff8e9', color: '#8b641c', fontSize: 12 }}>{selected.revokedReason}</div>
                ) : null}
              </div>

              <footer style={{ minHeight: 58, padding: '10px 20px', borderTop: '1px solid ' + colors.border, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 18, flexShrink: 0 }}>
                <div style={{ color: colors.muted, fontSize: 12 }}>
                  {view === 'pending'
                    ? selected.kind === 'knowledge_conflict'
                      ? '决定后将自动更新关系、图谱和索引，旧版本仍可恢复。'
                      : '合并后会保留来源证据；选择独立后，相同资料组合将复用本次结果。'
                    : selected.ruleStatus === 'active'
                      ? '相同资料与知识指纹再次触发时，将自动复用这次决定。'
                      : '该记录仅用于追溯，不再参与后续自动判断。'}
                </div>
                {view === 'pending' ? (
                  <div style={{ display: 'flex', gap: 9 }}>
                    <Button>{selected.kind === 'knowledge_conflict' ? '保留当前知识' : '保持页面独立'}</Button>
                    {selected.kind === 'knowledge_conflict' ? <Button>编辑后采用</Button> : null}
                    <Button type="primary">{selected.kind === 'knowledge_conflict' ? '使用新知识' : '确认合并'}</Button>
                  </div>
                ) : (
                  <Button onClick={() => switchView('pending')}>返回待决策</Button>
                )}
              </footer>
            </section>
          </div>
        </div>
      </main>
    </ConfigProvider>
  );
}

const meta = {
  title: 'OpsPilot/WikiDecisionRecordPrototype',
  component: DecisionRecordPrototype,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof DecisionRecordPrototype>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  args: {
    initialView: 'pending',
  },
};

export const HistoryFirst: Story = {
  args: {
    initialView: 'history',
  },
};
