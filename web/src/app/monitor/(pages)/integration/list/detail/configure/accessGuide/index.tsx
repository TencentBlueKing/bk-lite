'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Form,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag
} from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import { TemplateAccessGuideDoc } from '@/app/monitor/types/integration';
import { useUserInfoContext } from '@/context/userInfo';
import { Group } from '@/types/index';
import CodeEditor from '@/components/code-editor';
import { useCopy } from '@/hooks/useCopy';

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

const buildCurlExample = (
  endpoint: string,
  line: string
) => `curl -X POST '${endpoint}' \\
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

const buildJavascriptExample = (
  endpoint: string,
  line: string
) => `const endpoint = '${endpoint}';

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

const buildRequestParamDocs = (
  doc: TemplateAccessGuideDoc | null,
  t: (key: string) => string
) => [
  {
    key: 'organization_id',
    name: t('monitor.integrations.customApi.organizationIdName'),
    type: 'tag(number/string)',
    required: t('monitor.integrations.customApi.yes'),
    description: `${t('monitor.integrations.customApi.organizationIdDesc')}${doc?.organization_id || '--'}`
  },
  {
    key: 'instance_type',
    name: t('monitor.integrations.customApi.instanceTypeName'),
    type: 'tag(string)',
    required: t('monitor.integrations.customApi.yes'),
    description: `${t('monitor.integrations.customApi.instanceTypeDesc')}${doc?.instance_type || '--'}`
  },
  {
    key: 'plugin_id',
    name: t('monitor.integrations.customApi.pluginIdName'),
    type: 'tag(number/string)',
    required: t('monitor.integrations.customApi.yes'),
    description: `${t('monitor.integrations.customApi.pluginIdDesc')}${doc?.plugin_id || '--'}`
  },
  {
    key: 'instance_identifier',
    name: (doc?.instance_id_keys?.length || 0) > 1
      ? doc?.instance_id_keys.map((item) => `${item}=<value>`).join(', ')
      : `${doc?.instance_id_keys?.[0] || 'instance_id'}=<value>`,
    type: 'tag(string)',
    required: '是',
    description:
      (doc?.instance_id_keys?.length || 0) > 0
        ? `监控对象唯一标识维度，必须传入：${(doc?.instance_id_keys || []).join('、')}。当监控对象未配置 instance_id_keys 时，默认必传 instance_id。`
        : '监控对象唯一标识维度，默认必传 instance_id。'
  },
  {
    key: 'measurement',
    name: '<metric_name>',
    type: 'measurement',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.measurementDesc')
  },
  {
    key: 'field_value',
    name: t('monitor.integrations.customApi.fieldValueName'),
    type: 'field(number/string/boolean)',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.fieldValueDesc')
  },
  {
    key: 'timestamp',
    name: '<timestamp>',
    type: 'timestamp(ms)',
    required: t('monitor.integrations.customApi.no'),
    description: t('monitor.integrations.customApi.timestampParamDesc')
  },
  {
    key: 'extra_tags',
    name: t('monitor.integrations.customApi.extraTagsName'),
    type: 'tag(optional)',
    required: t('monitor.integrations.customApi.no'),
    description: t('monitor.integrations.customApi.extraTagsDesc')
  }
];

const TemplateAccessGuide: React.FC = () => {
  const { t } = useTranslation();
  const { copy } = useCopy();
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

  const requestParamDocs = useMemo(
    () => buildRequestParamDocs(doc, t),
    [doc, t]
  );

  const sampleExamples = useMemo(
    () => [
      {
        key: 'without_timestamp',
        title: t('monitor.integrations.customApi.exampleWithoutTimestamp'),
        line: lineProtocolExampleWithoutTimestamp
      },
      {
        key: 'with_timestamp_ms',
        title: t('monitor.integrations.customApi.exampleWithTimestampMs'),
        line: lineProtocolExampleWithTimestampMs
      }
    ],
    [lineProtocolExampleWithoutTimestamp, lineProtocolExampleWithTimestampMs, t]
  );

  return (
    <Spin spinning={loading}>
      <div className="px-[10px]">
        <Space direction="vertical" size={20} className="w-full">
          <div>
            <div className="mb-3 text-lg font-semibold">
              {t('monitor.integrations.customApi.accessConfig')}
            </div>
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
                <Form.Item
                  label={t('monitor.integrations.customApi.cloudRegion')}
                  required
                >
                  <div className="w-1/2 max-w-full">
                    <Select
                      value={selectedCloudRegion}
                      placeholder={t(
                        'monitor.integrations.customApi.selectCloudRegion'
                      )}
                      loading={cloudRegionLoading}
                      options={cloudRegionList.map((item) => ({
                        value: Number(item.id),
                        label: item.display_name || item.name
                      }))}
                      onChange={(value) => setSelectedCloudRegion(value)}
                    />
                  </div>
                </Form.Item>

                <Form.Item
                  label={t('monitor.integrations.customApi.organization')}
                  required
                  className="mb-0"
                >
                  <div className="w-1/2 max-w-full">
                    <Select
                      value={selectedOrganization}
                      placeholder={t(
                        'monitor.integrations.customApi.selectOrganization'
                      )}
                      options={organizationOptions}
                      onChange={(value) => setSelectedOrganization(value)}
                    />
                  </div>
                </Form.Item>
              </Form>
            </Card>
          </div>

          <div>
            <div className="mb-3 text-lg font-semibold">
              {t('monitor.integrations.customApi.apiEndpoint')}
            </div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
              <div className="flex w-full items-center gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 py-2">
                <Tag className="m-0 shrink-0 border-0 bg-[var(--color-success)] px-2 py-0.5 text-[12px] font-medium text-white">
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
                  onClick={() => copy(doc?.endpoint || '')}
                >
                  {t('common.copy')}
                </Button>
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 text-lg font-semibold">
              {t('monitor.integrations.customApi.requestExample')}
            </div>
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
                          ? buildJavascriptExample(
                            doc?.endpoint || '',
                            item.line
                          )
                          : buildCurlExample(doc?.endpoint || '', item.line);

                    return (
                      <div key={item.key}>
                        <div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">
                          {item.title}
                        </div>
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

          <div className="mb-[10px]">
            <div className="mb-3 text-lg font-semibold">
              {t('monitor.integrations.customApi.requestParamsDesc')}
            </div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
              <Table
                rowKey="key"
                pagination={false}
                dataSource={requestParamDocs}
                columns={[
                  {
                    title: t('monitor.integrations.customApi.param'),
                    dataIndex: 'name',
                    key: 'name'
                  },
                  {
                    title: t('monitor.integrations.customApi.type'),
                    dataIndex: 'type',
                    key: 'type'
                  },
                  {
                    title: t('monitor.integrations.customApi.required'),
                    dataIndex: 'required',
                    key: 'required'
                  },
                  {
                    title: t('monitor.integrations.customApi.description'),
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
