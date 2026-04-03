'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Card, Form, Select, Space, Spin, Table, Tabs, Tag } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import { TemplateAccessGuideDoc } from '@/app/monitor/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import { Group } from '@/types/index';
import CodeEditor from '@/app/monitor/components/codeEditor';

type SampleFormat = 'curl' | 'python' | 'javascript';

const escapeSingleQuotes = (value: string) => value.replace(/'/g, `'"'"'`);

const getGroupDisplayPath = (group: Group, flatGroups: Group[]) => {
  const names: string[] = [];
  let current: Group | undefined = group;

  while (current) {
    if (current.name) {
      names.unshift(current.name);
    }

    const parentId =
      (current as Group & { parent_id?: string }).parent_id || current.parentId;
    current = parentId
      ? flatGroups.find((item) => item.id === parentId)
      : undefined;
  }

  return names.join('/');
};

const buildCurlExample = (endpoint: string, line: string) => `curl -X POST '${endpoint}' \\
  -H 'Content-Type: text/plain' \\
  --data-binary '${escapeSingleQuotes(line)}'`;

const buildPythonExample = (endpoint: string, line: string) => `import requests

url = '${endpoint}'
headers = {
    'Content-Type': 'text/plain'
}
payload = '${line}'

response = requests.post(url, headers=headers, data=payload.encode('utf-8'), timeout=10)
print(response.status_code)
print(response.text)`;

const buildJavascriptExample = (endpoint: string, line: string) => `const endpoint = '${endpoint}';

const payload = '${line}';

const response = await fetch(endpoint, {
  method: 'POST',
  headers: {
    'Content-Type': 'text/plain'
  },
  body: payload
});

console.log(response.status);
console.log(await response.text());`;

const buildRequestParamDocs = (doc: TemplateAccessGuideDoc | null) => [
  {
    key: 'organization_id',
    name: 'organization_id=<组织ID>',
    type: 'tag(number/string)',
    required: '是',
    description: `组织 ID 标签，固定为当前选择的组织，例如 ${doc?.organization_id || '--'}`
  },
  {
    key: 'instance_type',
    name: 'instance_type=<对象类型>',
    type: 'tag(string)',
    required: '是',
    description: `对象类型标签，固定为当前模板绑定对象类型，例如 ${doc?.instance_type || '--'}`
  },
  {
    key: 'plugin_id',
    name: 'plugin_id=<模板ID>',
    type: 'tag(number/string)',
    required: '是',
    description: `插件模板 ID 标签，固定为当前模板 ID，例如 ${doc?.plugin_id || '--'}`
  },
  {
    key: 'measurement',
    name: '<metric_name>',
    type: 'measurement',
    required: '是',
    description: '行协议中的 measurement，建议直接使用模板中定义的指标名称'
  },
  {
    key: 'field_value',
    name: 'value=<指标值>',
    type: 'field(number/string/boolean)',
    required: '是',
    description: '指标值字段，字段名建议固定使用 value'
  },
  {
    key: 'timestamp',
    name: '<timestamp>',
    type: 'timestamp(ms)',
    required: '否',
    description: '可选时间戳；不传时默认使用服务端接收时间，传入时推荐使用 13 位毫秒时间戳，例如 1712052000000'
  },
  {
    key: 'extra_tags',
    name: '<extra_tag>=<value>',
    type: 'tag(optional)',
    required: '否',
    description: '可选扩展标签，可按业务需要继续追加在 measurement 后面'
  }
];

const copyText = async (text: string) => {
  if (!text) return;
  await navigator.clipboard.writeText(text);
};

const TemplateAccessGuide: React.FC = () => {
  useTranslation();
  const searchParams = useSearchParams();
  const pluginId = searchParams.get('plugin_id') || '';
  const { getTemplateAccessGuide, getCloudRegionList } = useIntegrationApi();
  const userInfo = useUserInfoContext();
  const [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<TemplateAccessGuideDoc | null>(null);
  const [sampleFormat, setSampleFormat] = useState<SampleFormat>('curl');
  const [cloudRegionLoading, setCloudRegionLoading] = useState(false);
  const [cloudRegionList, setCloudRegionList] = useState<any[]>([]);
  const [selectedOrganization, setSelectedOrganization] = useState<number>();
  const [selectedCloudRegion, setSelectedCloudRegion] = useState<number>();

  const organizationOptions = useMemo(
    () =>
      (userInfo.flatGroups || []).map((item) => ({
        value: Number(item.id),
        label: getGroupDisplayPath(item, userInfo.flatGroups || []) || item.name
      })),
    [userInfo.flatGroups]
  );

  useEffect(() => {
    if (userInfo?.selectedGroup?.id) {
      setSelectedOrganization(Number(userInfo.selectedGroup.id));
    }
  }, [userInfo?.selectedGroup?.id]);

  useEffect(() => {
    const fetchCloudRegions = async () => {
      setCloudRegionLoading(true);
      try {
        const data = await getCloudRegionList({ page_size: -1 });
        const nextList = data || [];
        setCloudRegionList(nextList);
        if (!selectedCloudRegion && nextList.length) {
          setSelectedCloudRegion(Number(nextList[0].id));
        }
      } finally {
        setCloudRegionLoading(false);
      }
    };

    fetchCloudRegions();
  }, []);

  useEffect(() => {
    const fetchDoc = async () => {
      if (!pluginId || !selectedOrganization || !selectedCloudRegion) {
        return;
      }
      setLoading(true);
      try {
        const data = await getTemplateAccessGuide(pluginId, {
          organization_id: selectedOrganization,
          cloud_region_id: selectedCloudRegion
        });
        setDoc(data);
      } finally {
        setLoading(false);
      }
    };

    fetchDoc();
  }, [pluginId, selectedOrganization, selectedCloudRegion]);

  const lineProtocolExample = useMemo(
    () => doc?.line_protocol_example || '',
    [doc?.line_protocol_example]
  );

  const lineProtocolExampleWithoutTimestamp = useMemo(
    () => doc?.line_protocol_example_without_timestamp || lineProtocolExample,
    [doc?.line_protocol_example_without_timestamp, lineProtocolExample]
  );

  const lineProtocolExampleWithTimestampMs = useMemo(
    () => doc?.line_protocol_example_with_timestamp_ms || lineProtocolExample,
    [doc?.line_protocol_example_with_timestamp_ms, lineProtocolExample]
  );

  const sampleCode = useMemo(() => {
    const endpoint = doc?.endpoint || '';
    if (sampleFormat === 'python') {
      return buildPythonExample(endpoint, lineProtocolExample);
    }
    if (sampleFormat === 'javascript') {
      return buildJavascriptExample(endpoint, lineProtocolExample);
    }
    return buildCurlExample(endpoint, lineProtocolExample);
  }, [doc?.endpoint, lineProtocolExample, sampleFormat]);

  const requestParamDocs = useMemo(() => buildRequestParamDocs(doc), [doc]);

  const sampleExamples = useMemo(
    () => [
      {
        key: 'without_timestamp',
        title: '示例一：不传时间戳（推荐使用服务端接收时间）',
        line: lineProtocolExampleWithoutTimestamp
      },
      {
        key: 'with_timestamp_ms',
        title: '示例二：传入 13 位毫秒时间戳',
        line: lineProtocolExampleWithTimestampMs
      }
    ],
    [lineProtocolExampleWithoutTimestamp, lineProtocolExampleWithTimestampMs]
  );

  return (
    <Spin spinning={loading}>
      <div className="px-[10px]">
        <Space direction="vertical" size={20} className="w-full">
          <div>
            <div className="mb-3 text-lg font-semibold">接入配置</div>
            <Card
              style={{
                background: 'var(--color-fill-1)',
                borderColor: 'var(--color-border)'
              }}
              styles={{
                body: {
                  background: 'var(--color-fill-1)',
                  padding: 16
                }
              }}
            >
              <Form layout="vertical" requiredMark>
                <Form.Item label="云区域" required>
                  <div className="w-1/2 max-w-full">
                    <Select
                      value={selectedCloudRegion}
                      placeholder="请选择云区域"
                      loading={cloudRegionLoading}
                      options={cloudRegionList.map((item) => ({
                        value: Number(item.id),
                        label: item.display_name || item.name
                      }))}
                      onChange={(value) => setSelectedCloudRegion(value)}
                    />
                  </div>
                </Form.Item>

                <Form.Item label="组织" required className="mb-0">
                  <div className="w-1/2 max-w-full">
                    <Select
                      value={selectedOrganization}
                      placeholder="请选择组织"
                      options={organizationOptions}
                      onChange={(value) => setSelectedOrganization(value)}
                    />
                  </div>
                </Form.Item>
              </Form>
            </Card>
          </div>

          <div>
            <div className="mb-3 text-lg font-semibold">API端点</div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
              <div className="flex w-full items-center gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 py-2">
                <Tag className="m-0 shrink-0 border-0 bg-[#34d399] px-2 py-0.5 text-[12px] font-medium text-white">
                  POST
                </Tag>
                <div className="min-w-0 flex-1 rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-1.5">
                  <span
                    className="block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[13px] text-[var(--color-text-1)]"
                    title={doc?.endpoint || '--'}
                  >
                    {doc?.endpoint || '--'}
                  </span>
                </div>
                <Button
                  type="default"
                  icon={<CopyOutlined />}
                  className="shrink-0"
                  disabled={!doc?.endpoint}
                  onClick={() => copyText(doc?.endpoint || '')}
                >
                  复制
                </Button>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 text-lg font-semibold">请求示例</div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)]">
              <Tabs
                activeKey={sampleFormat}
                onChange={(key) => setSampleFormat(key as SampleFormat)}
                className="px-4"
                items={[
                  { label: 'cURL', key: 'curl' },
                  { label: 'Python', key: 'python' },
                  { label: 'JavaScript', key: 'javascript' }
                ]}
              />
              <div className="px-4 pb-4">
                <Space direction="vertical" size={16} className="w-full">
                  {sampleExamples.map((item) => {
                    const exampleCode =
                      sampleFormat === 'python'
                        ? buildPythonExample(doc?.endpoint || '', item.line)
                        : sampleFormat === 'javascript'
                          ? buildJavascriptExample(doc?.endpoint || '', item.line)
                          : buildCurlExample(doc?.endpoint || '', item.line);

                    return (
                      <div key={item.key}>
                        <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">{item.title}</div>
                        <CodeEditor
                          value={exampleCode}
                          mode={sampleFormat === 'python' ? 'python' : 'shell'}
                          theme="monokai"
                          readOnly
                          width="100%"
                          height="220px"
                          headerOptions={{ copy: true, fullscreen: true }}
                        />
                      </div>
                    );
                  })}
                </Space>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 text-lg font-semibold">请求参数说明</div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
              <Table
                rowKey="key"
                pagination={false}
                dataSource={requestParamDocs}
                columns={[
                  { title: '参数', dataIndex: 'name', key: 'name' },
                  { title: '类型', dataIndex: 'type', key: 'type' },
                  { title: '必填', dataIndex: 'required', key: 'required' },
                  {
                    title: '说明',
                    dataIndex: 'description',
                    key: 'description'
                  }
                ]}
              />
            </div>
          </div>
        </Space>
      </div>
    </Spin>
  );
};

export default TemplateAccessGuide;
