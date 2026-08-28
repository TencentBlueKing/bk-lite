'use client';

/**
 * Provider 详情 After — 对齐生产 Tabs、基础信息表单与四类模型分区。
 */

import { useState } from 'react';
import { Button, Form, Input, Select, Switch, Tabs } from 'antd';
import { ArrowLeftOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import { AfterSectionCard } from './opspilot-after-system';

const { TextArea } = Input;

type ModelKind = 'llm' | 'embed' | 'rerank' | 'ocr';

interface ModelRow {
  id: number;
  name: string;
  modelId: string;
  teams: string;
  multimodal?: boolean;
  enabled: boolean;
}

const VENDOR_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure', label: 'Azure' },
  { value: 'aliyun', label: '阿里云' },
  { value: 'deepseek', label: 'DeepSeek' },
];

const SECTION_META: Array<{ key: ModelKind; title: string }> = [
  { key: 'llm', title: 'LLM模型' },
  { key: 'embed', title: '向量模型' },
  { key: 'rerank', title: '重排模型' },
  { key: 'ocr', title: '图像模型' },
];

const INITIAL_MODELS: Record<ModelKind, ModelRow[]> = {
  llm: [
    { id: 1, name: 'GPT-4o', modelId: 'gpt-4o', teams: 'Default', multimodal: true, enabled: true },
    { id: 2, name: 'GPT-4o mini', modelId: 'gpt-4o-mini', teams: 'Default', multimodal: true, enabled: true },
  ],
  embed: [
    { id: 3, name: 'Embedding 3', modelId: 'text-embedding-3-large', teams: 'Default', enabled: false },
  ],
  rerank: [],
  ocr: [],
};

function BasicInfoTab() {
  return (
    <div>
      <div className="mb-4">
        <div className="text-sm font-medium text-[var(--color-text-1)]">基础信息</div>
        <div className="mt-1 text-xs text-[var(--color-text-3)]">展示供应商接入信息</div>
      </div>

      <Form layout="vertical" initialValues={{
        name: 'OpenAI Production',
        vendor_type: 'openai',
        api_base: 'https://api.openai.com/v1',
        api_key: '*******',
        team: ['Default'],
        description: '生产对话与嵌入共用接入。',
        enabled: true,
      }}>
        <div className="grid grid-cols-1 gap-x-4 xl:grid-cols-2">
          <Form.Item label="名称" name="name" required>
            <Input placeholder="例如：OpenAI 官方、研发部专用" />
          </Form.Item>
          <Form.Item label="类型" name="vendor_type" required>
            <Select options={VENDOR_OPTIONS} />
          </Form.Item>
        </div>

        <Form.Item label="API 地址" name="api_base" required>
          <Input placeholder="请输入 API 地址" />
        </Form.Item>

        <Form.Item label="API Key" required>
          <div className="flex items-start gap-3">
            <Form.Item name="api_key" className="mb-0 flex-1">
              <Input.Password visibilityToggle={false} />
            </Form.Item>
            <Button className="mt-px">测试链接</Button>
          </div>
        </Form.Item>

        <Form.Item label="组织" name="team" required>
          <Select
            mode="multiple"
            placeholder="请选择组织"
            options={[
              { value: 'Default', label: 'Default' },
              { value: 'SRE', label: 'SRE' },
              { value: '平台运维', label: '平台运维' },
            ]}
          />
        </Form.Item>

        <Form.Item label="简介" name="description">
          <TextArea rows={4} placeholder="可选，填写该供应商的用途说明" />
        </Form.Item>

        <Form.Item label="启用状态" name="enabled" valuePropName="checked">
          <Switch size="small" />
        </Form.Item>

        <div className="flex justify-end gap-3 pt-4">
          <Button>测试链接</Button>
          <Button type="primary">保存</Button>
        </div>
      </Form>
    </div>
  );
}

function ModelSection({
  title,
  kind,
  models,
  onToggle,
}: {
  title: string;
  kind: ModelKind;
  models: ModelRow[];
  onToggle: (kind: ModelKind, id: number, enabled: boolean) => void;
}) {
  const isLlm = kind === 'llm';
  const grid = isLlm
    ? 'grid-cols-[1.2fr_1.4fr_1fr_88px_88px_100px]'
    : 'grid-cols-[1.2fr_1.4fr_1fr_88px_100px]';

  return (
    <AfterSectionCard
      className="flex min-h-[240px] flex-col"
      title={
        <span className="flex items-center gap-2">
          {title}
          <span className="text-xs font-normal text-[var(--color-text-3)]">共{models.length}个</span>
        </span>
      }
      extra={
        <Button type="primary" ghost size="small" icon={<PlusOutlined />}>
          新增
        </Button>
      }
    >
      {models.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-4 py-8 text-sm text-[var(--color-text-3)]">
          暂无模型，点击 + 新增
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <div className="min-w-160">
            <div className={`grid border-b border-[var(--color-border-1)] px-4 py-2 text-[12px] font-medium text-[var(--color-text-3)] ${grid}`}>
              <span>模型名称</span>
              <span>模型 ID</span>
              <span>可用组织</span>
              {isLlm ? <span>支持多模态</span> : null}
              <span>启停</span>
              <span>编辑</span>
            </div>
            {models.map((model) => (
              <div
                key={model.id}
                className={`grid items-center border-b border-[var(--color-border-1)] px-4 py-2.5 text-[13px] text-[var(--color-text-2)] ${grid}`}
              >
                <span className="truncate pr-3">{model.name}</span>
                <span className="truncate pr-3">{model.modelId}</span>
                <span className="truncate pr-3">{model.teams}</span>
                {isLlm ? <span>{model.multimodal ? '是' : '否'}</span> : null}
                <span>
                  <Switch
                    size="small"
                    checked={model.enabled}
                    onChange={(checked) => onToggle(kind, model.id, checked)}
                  />
                </span>
                <span className="flex items-center gap-1">
                  <Button type="text" size="small" icon={<EditOutlined />} />
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </AfterSectionCard>
  );
}

function ModelManagementTab() {
  const [models, setModels] = useState(INITIAL_MODELS);

  const handleToggle = (kind: ModelKind, id: number, enabled: boolean) => {
    setModels((prev) => ({
      ...prev,
      [kind]: prev[kind].map((item) => (item.id === id ? { ...item, enabled } : item)),
    }));
  };

  return (
    <div className="flex min-h-[520px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Input.Search allowClear enterButton placeholder="搜索模型ID或名称" className="w-full max-w-[320px]" />
        <Button>同步模型</Button>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {SECTION_META.map((section) => (
          <ModelSection
            key={section.key}
            kind={section.key}
            title={section.title}
            models={models[section.key]}
            onToggle={handleToggle}
          />
        ))}
      </div>
    </div>
  );
}

export function ProviderDetailWorkbench() {
  return (
    <div className="w-full rounded-3xl bg-[var(--color-bg)] p-5 shadow-sm lg:p-6">
      <div className="mb-2 flex items-center gap-2 text-xs text-[var(--color-text-3)]">
        <span>供应商</span>
        <span>/</span>
        <span>OpenAI Production</span>
      </div>

      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button icon={<ArrowLeftOutlined />} type="text" size="small" />
          <span className="text-[16px] font-semibold text-[var(--color-text-1)]">OpenAI Production</span>
        </div>
        <span className="text-xs text-[var(--color-text-3)]">类型: OpenAI</span>
      </div>

      <Tabs
        defaultActiveKey="models"
        items={[
          { key: 'basic', label: '基础信息', children: <BasicInfoTab /> },
          { key: 'models', label: '模型管理', children: <ModelManagementTab /> },
        ]}
      />
    </div>
  );
}
