'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Space,
  Spin,
  Tabs,
  Tag,
  message
} from 'antd';
import { CopyOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import useMonitorApi from '@/app/monitor/api';
import {
  PushAccessDoc,
  PushAccessInstanceItem
} from '@/app/monitor/types/integration';
import ExcelImportModal, { ExcelImportModalRef } from '../excelImportModal';
import { Organization } from '@/app/monitor/types';
import { useCommon } from '@/app/monitor/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import { Group } from '@/types/index';
import { useCopy } from '@/hooks/useCopy';
import CodeEditor from '@/app/monitor/components/codeEditor';
import CustomTable from '@/components/custom-table';
import GroupTreeSelector from '@/components/group-tree-select';
import SelectAssetModal, { SelectAssetModalRef } from './selectAssetModal';
import CreateAssetModal, { CreateAssetModalRef } from './createAssetModal';

type SampleFormat = 'curl' | 'python' | 'javascript';

const formatJson = (value: Record<string, any>) =>
  JSON.stringify(value, null, 2);

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
  token: string,
  payload: Record<string, any>
) => {
  const payloadText = JSON.stringify(payload, null, 2)
    .split('\n')
    .map((line) => `  ${line}`)
    .join(' \\\n');

  return `curl -X POST '${endpoint}' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer ${token || '<API_TOKEN>'}' \\
  -d '${payloadText}\n  '`;
};

const buildPythonExample = (
  endpoint: string,
  token: string,
  payload: Record<string, any>
) => `import requests

url = '${endpoint}'
headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ${token || '<API_TOKEN>'}'
}
payload = ${formatJson(payload)}

response = requests.post(url, headers=headers, json=payload, timeout=10)
print(response.status_code)
print(response.json())`;

const buildJavascriptExample = (
  endpoint: string,
  token: string,
  payload: Record<string, any>
) => `const endpoint = '${endpoint}';

const payload = ${formatJson(payload)};

const response = await fetch(endpoint, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: 'Bearer ${token || '<API_TOKEN>'}'
  },
  body: JSON.stringify(payload)
});

const result = await response.json();
console.log(result);`;

const buildRequestParamDocs = (
  doc: PushAccessDoc | null,
  t: (key: string) => string
) => [
  {
    key: 'template_id',
    name: 'template_id',
    type: 'string',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.templateIdDesc').replace(
      '{{templateId}}',
      doc?.template_id || '--'
    )
  },
  {
    key: 'token',
    name: 'token',
    type: 'string',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.tokenDesc')
  },
  {
    key: 'timestamp',
    name: 'timestamp',
    type: 'number',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.timestampDesc')
  },
  {
    key: 'instances',
    name: 'instances[]',
    type: 'array',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.instancesDesc')
  },
  {
    key: 'instance_id',
    name: 'instances[].instance_id',
    type: 'string',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.instanceIdDesc')
  },
  ...(doc?.instance_id_keys || [])
    .filter((key) => key !== 'instance_id')
    .map((key) => ({
      key: `instance_key_${key}`,
      name: `instances[].${key}`,
      type: 'string',
      required: t('monitor.integrations.customApi.yes'),
      description: t('monitor.integrations.customApi.instanceKeyDesc').replace(
        '{{key}}',
        key
      )
    })),
  {
    key: 'metrics',
    name: 'instances[].metrics[]',
    type: 'array',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.metricsDesc')
  },
  {
    key: 'metric_name',
    name: 'instances[].metrics[].name',
    type: 'string',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.metricNameDesc')
  },
  {
    key: 'metric_value',
    name: 'instances[].metrics[].value',
    type: 'number | string | boolean',
    required: t('monitor.integrations.customApi.yes'),
    description: t('monitor.integrations.customApi.metricValueDesc')
  },
  {
    key: 'metric_timestamp',
    name: 'instances[].metrics[].timestamp',
    type: 'number',
    required: t('monitor.integrations.customApi.no'),
    description: t('monitor.integrations.customApi.metricTimestampDesc')
  },
  {
    key: 'metric_tags',
    name: 'instances[].metrics[].tags',
    type: 'object',
    required: t('monitor.integrations.customApi.no'),
    description: t('monitor.integrations.customApi.metricTagsDesc')
  }
];

const copyText = async (text: string, successText: string) => {
  if (!text) return;
  await navigator.clipboard.writeText(text);
  message.success(successText);
};

const parseInternalInstanceId = (
  internalInstanceId: string,
  instanceIdKeys: string[]
) => {
  const keys = instanceIdKeys?.length ? instanceIdKeys : ['instance_id'];
  const rawDimensions: Record<string, string> = {};

  if (!internalInstanceId) {
    return rawDimensions;
  }

  const quotedValues = Array.from(
    internalInstanceId.matchAll(/'([^']*)'|"([^"]*)"/g)
  ).map((match) => match[1] ?? match[2] ?? '');

  const values = quotedValues.length ? quotedValues : [internalInstanceId];

  keys.forEach((key, index) => {
    rawDimensions[key] = values[index] || '';
  });

  return rawDimensions;
};

const buildInstanceIdentityLabel = (
  instance: PushAccessInstanceItem,
  instanceIdKeys: string[]
) => {
  const rawInstance =
    instance.raw_instance ||
    parseInternalInstanceId(instance.instance_id || '', instanceIdKeys);
  const keys = instanceIdKeys?.length ? instanceIdKeys : ['instance_id'];
  return keys.map((key) => rawInstance[key] || '--').join(' / ');
};

const CustomApiAccess: React.FC = () => {
  const { t } = useTranslation();
  const { copy } = useCopy();
  const searchParams = useSearchParams();
  const pluginId = searchParams.get('plugin_id') || '';
  const objectId = Number(searchParams.get('id') || 0);
  const { getPushAccessDoc, getCurrentApiSecret, createK8sInstance } =
    useIntegrationApi();
  const { getInstanceList } = useMonitorApi();
  const commonContext = useCommon();
  const userInfo = useUserInfoContext();
  const organizationList = useRef<Organization[]>(
    commonContext?.authOrganizations || []
  );
  const importRef = useRef<ExcelImportModalRef>(null);
  const selectAssetRef = useRef<SelectAssetModalRef>(null);
  const createAssetRef = useRef<CreateAssetModalRef>(null);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [doc, setDoc] = useState<PushAccessDoc | null>(null);
  const [instances, setInstances] = useState<PushAccessInstanceItem[]>([]);
  const [selectedOrganization, setSelectedOrganization] = useState<number>();
  const [selectedInstanceIds, setSelectedInstanceIds] = useState<React.Key[]>(
    []
  );
  const [sampleFormat, setSampleFormat] = useState<SampleFormat>('curl');
  const [apiSecret, setApiSecret] = useState('');
  const [apiSecretExists, setApiSecretExists] = useState(true);

  const organizationNameMap = useMemo(
    () =>
      new Map(
        (userInfo.flatGroups || []).map((item) => [
          String(item.id),
          getGroupDisplayPath(item, userInfo.flatGroups || []) ||
            item.name ||
            String(item.id)
        ])
      ),
    [userInfo.flatGroups]
  );

  useEffect(() => {
    if (userInfo?.selectedGroup?.id) {
      setSelectedOrganization(Number(userInfo.selectedGroup.id));
    }
  }, [userInfo?.selectedGroup?.id]);

  const fetchDoc = async (team?: number) => {
    if (!pluginId) return;
    setLoading(true);
    try {
      const data = await getPushAccessDoc(
        pluginId,
        team ? { team } : undefined
      );
      setDoc(data);
      setApiSecret(data?.api_secret || '');
      setApiSecretExists(Boolean(data?.api_secret_exists));
    } finally {
      setLoading(false);
    }
  };

  const fetchSecret = async (team?: number) => {
    if (!team) return;
    const data = await getCurrentApiSecret({ team });
    setApiSecret(data?.api_secret || '');
    setApiSecretExists(Boolean(data?.exists));
  };

  const fetchInstances = async () => {
    if (!objectId) return [];
    try {
      const data = await getInstanceList(objectId, { page_size: -1 });
      const nextInstances = data?.results || [];
      setInstances(nextInstances);
      return nextInstances;
    } catch {
      return [];
    }
  };

  useEffect(() => {
    if (!selectedOrganization) return;
    fetchDoc(selectedOrganization);
  }, [pluginId, selectedOrganization]);

  useEffect(() => {
    fetchInstances();
  }, [objectId]);

  useEffect(() => {
    if (!selectedOrganization) return;
    fetchSecret(selectedOrganization);
  }, [selectedOrganization]);

  const availableInstances = useMemo(() => {
    if (!selectedOrganization) return instances;
    return instances.filter((item) => {
      const orgValues = item.organization || item.organizations || [];
      return orgValues.map(Number).includes(Number(selectedOrganization));
    });
  }, [instances, selectedOrganization]);

  const selectedAssets = useMemo(() => {
    const selectedSet = new Set(selectedInstanceIds.map(String));
    return availableInstances.filter((item) =>
      selectedSet.has(String(item.instance_id))
    );
  }, [availableInstances, selectedInstanceIds]);

  useEffect(() => {
    setSelectedInstanceIds((prev) => {
      const availableIdSet = new Set(
        availableInstances.map((item) => String(item.instance_id))
      );
      return prev.filter((item) => availableIdSet.has(String(item)));
    });
  }, [availableInstances]);

  const payloadExample = useMemo(() => {
    const source = doc?.payload_example || {};
    const selectedInstance = selectedAssets[0];
    const defaultMetric = doc?.metrics?.[0];
    const selectedRawInstance = selectedInstance?.raw_instance || {};
    const sourceInstance = source.instances?.[0] || {};
    const instanceIdKeys = doc?.instance_id_keys || ['instance_id'];
    const normalizedInstance = instanceIdKeys.reduce<Record<string, any>>(
      (acc, key) => {
        acc[key] =
          selectedRawInstance[key] ||
          sourceInstance[key] ||
          (key === 'instance_id' ? 'demo-instance-id' : `demo-${key}`);
        return acc;
      },
      {}
    );

    return {
      ...source,
      organization: selectedOrganization || source.organization,
      token: apiSecret || '<API_TOKEN>',
      instances: [
        {
          ...sourceInstance,
          ...normalizedInstance,
          metrics: [
            {
              name:
                defaultMetric?.name ||
                source.instances?.[0]?.metrics?.[0]?.name ||
                'demo_metric',
              value: source.instances?.[0]?.metrics?.[0]?.value ?? 1,
              tags: source.instances?.[0]?.metrics?.[0]?.tags || {}
            }
          ]
        }
      ]
    };
  }, [doc, selectedAssets, selectedOrganization, apiSecret]);

  const sampleCode = useMemo(() => {
    const endpoint =
      doc?.endpoint || '/api/v1/monitor/open_api/push_api/report/';
    if (sampleFormat === 'python') {
      return buildPythonExample(endpoint, apiSecret, payloadExample);
    }
    if (sampleFormat === 'javascript') {
      return buildJavascriptExample(endpoint, apiSecret, payloadExample);
    }
    return buildCurlExample(endpoint, apiSecret, payloadExample);
  }, [doc?.endpoint, apiSecret, payloadExample, sampleFormat]);

  const handleImport = async (rows: any[]) => {
    if (!selectedOrganization) return;
    setSubmitting(true);
    try {
      const createdIds: React.Key[] = [];
      for (const row of rows) {
        const result = await createK8sInstance({
          organizations: [selectedOrganization],
          id: row.id,
          name: row.instance_name,
          monitor_object_id: objectId
        });
        if (result?.instance_id) {
          createdIds.push(result.instance_id);
        }
      }
      message.success(t('common.importSuccess'));
      await fetchInstances();
      setSelectedInstanceIds((prev) =>
        Array.from(new Set([...prev, ...createdIds]))
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleSelectAssetConfirm = (selectedIds: React.Key[]) => {
    setSelectedInstanceIds(selectedIds);
  };

  const handleCreateAssetConfirm = async (createdInstanceId?: string) => {
    const latestInstances = await fetchInstances();
    if (createdInstanceId) {
      setSelectedInstanceIds((prev) =>
        Array.from(new Set([...prev, createdInstanceId]))
      );
    } else {
      const newest = latestInstances[latestInstances.length - 1];
      if (newest?.instance_id) {
        setSelectedInstanceIds((prev) =>
          Array.from(new Set([...prev, newest.instance_id]))
        );
      }
    }
  };

  const openSelectAssetsModal = () => {
    selectAssetRef.current?.showModal({
      instanceIdKeys: doc?.instance_id_keys || ['instance_id'],
      selectedInstanceIds,
      organizationNameMap,
      objectId,
      selectedOrganization
    });
  };

  const openCreateAssetModal = () => {
    createAssetRef.current?.showModal({
      selectedOrganization,
      objectId
    });
  };

  const requestParamDocs = useMemo(
    () => buildRequestParamDocs(doc, t),
    [doc, t]
  );

  const successResponse = useMemo(
    () =>
      formatJson({
        result: true,
        data: {
          template_id: doc?.template_id,
          accepted_metric_count: 1,
          filtered_count: 0,
          filtered_details: []
        },
        message: 'success'
      }),
    [doc?.template_id]
  );

  const errorResponse = useMemo(
    () =>
      formatJson({
        result: false,
        code: '400',
        message: 'template_id不能为空',
        data: null
      }),
    []
  );

  const renderOrganizationText = (record: PushAccessInstanceItem) => {
    const orgValues = record.organization || record.organizations || [];
    if (!orgValues.length) return '--';
    return orgValues
      .map(
        (item: string | number) => organizationNameMap.get(String(item)) || item
      )
      .join(', ');
  };

  const selectedAssetsColumns = [
    {
      title: t('monitor.integrations.customApi.assetName'),
      dataIndex: 'instance_name',
      key: 'instance_name',
      width: 200
    },
    {
      title: t('monitor.integrations.customApi.assetId'),
      dataIndex: 'instance_id',
      key: 'instance_id',
      width: 260,
      render: (_: string, record: PushAccessInstanceItem) => (
        <span className="font-mono text-[13px] text-[var(--color-text-1)]">
          {buildInstanceIdentityLabel(
            record,
            doc?.instance_id_keys || ['instance_id']
          )}
        </span>
      )
    },
    {
      title: t('monitor.integrations.customApi.belongOrganization'),
      dataIndex: 'organization',
      key: 'organization',
      width: 200,
      render: (_: any, record: PushAccessInstanceItem) =>
        renderOrganizationText(record)
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 80,
      render: (_: any, record: PushAccessInstanceItem) => (
        <Button
          type="link"
          className="px-0"
          onClick={() =>
            setSelectedInstanceIds((prev) =>
              prev.filter((id) => id !== record.instance_id)
            )
          }
        >
          {t('monitor.integrations.customApi.remove')}
        </Button>
      )
    }
  ];

  const requestParamColumns = [
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
  ];

  return (
    <Spin spinning={loading || submitting}>
      <div className="px-[10px]">
        <Space direction="vertical" size={20} className="w-full">
          {!apiSecretExists && (
            <Alert
              type="warning"
              showIcon
              message={t('monitor.integrations.customApi.noApiKeyWarning')}
            />
          )}

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
                  label={t('monitor.integrations.customApi.organization')}
                  required
                >
                  <div className="w-1/2 max-w-full">
                    <GroupTreeSelector
                      value={selectedOrganization ? [selectedOrganization] : []}
                      onChange={(value) => {
                        const numValue = Array.isArray(value)
                          ? value[0]
                          : value;
                        setSelectedOrganization(
                          numValue ? Number(numValue) : undefined
                        );
                      }}
                      multiple={false}
                      placeholder={t(
                        'monitor.integrations.customApi.selectOrganization'
                      )}
                    />
                  </div>
                </Form.Item>

                <Form.Item
                  label={t('monitor.integrations.customApi.apiKey')}
                  required
                >
                  <div className="flex w-full items-center gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 py-2">
                    <span className="shrink-0 text-[13px] text-[var(--color-primary)]">
                      {t('monitor.integrations.customApi.token')}
                    </span>
                    <div className="min-w-0 flex-1 rounded border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-1.5">
                      <span
                        className="block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[13px] text-[var(--color-text-1)]"
                        title={apiSecret || '--'}
                      >
                        {apiSecret || '--'}
                      </span>
                    </div>
                    <Button
                      type="default"
                      icon={<CopyOutlined />}
                      className="shrink-0"
                      disabled={!apiSecret}
                      onClick={() => copy(apiSecret)}
                    >
                      {t('common.copy')}
                    </Button>
                  </div>
                </Form.Item>

                <Form.Item
                  label={t('monitor.integrations.customApi.monitorAssets')}
                  required
                  className="mb-0"
                >
                  <Space direction="vertical" size={16} className="w-full">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Button
                          icon={<PlusOutlined />}
                          type="primary"
                          onClick={openCreateAssetModal}
                        >
                          {t('monitor.integrations.customApi.newAsset')}
                        </Button>
                        <Button
                          icon={<PlusOutlined />}
                          onClick={openSelectAssetsModal}
                        >
                          {t(
                            'monitor.integrations.customApi.selectExistingAsset'
                          )}
                        </Button>
                        {selectedAssets.length > 0 && (
                          <span className="text-[var(--color-text-3)]">
                            {t(
                              'monitor.integrations.customApi.selectedAssetsHint'
                            ).replace(
                              '{{count}}',
                              String(selectedAssets.length)
                            )}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          icon={<UploadOutlined />}
                          type="primary"
                          onClick={() =>
                            importRef.current?.showModal({
                              title: t('common.import'),
                              columns: [
                                {
                                  name: 'id',
                                  label: 'ID',
                                  required: true,
                                  is_only: true
                                },
                                {
                                  name: 'instance_name',
                                  label: t(
                                    'monitor.integrations.customApi.instanceName'
                                  ),
                                  required: true
                                }
                              ],
                              groupList: organizationList.current
                            })
                          }
                        >
                          {t('monitor.integrations.customApi.importNewAssets')}
                        </Button>
                        <Button
                          onClick={() => setSelectedInstanceIds([])}
                          disabled={!selectedInstanceIds.length}
                        >
                          {t('monitor.integrations.customApi.clearSelection')}
                        </Button>
                      </div>
                    </div>

                    {selectedAssets.length ? (
                      <CustomTable
                        rowKey="instance_id"
                        dataSource={selectedAssets}
                        columns={selectedAssetsColumns}
                        scroll={{ y: 'calc(100vh - 600px)' }}
                      />
                    ) : (
                      <div
                        className="flex items-center justify-center"
                        style={{ minHeight: '240px' }}
                      >
                        <Empty
                          description={t(
                            'monitor.integrations.customApi.selectOrCreateAsset'
                          )}
                        />
                      </div>
                    )}
                  </Space>
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
                  onClick={() =>
                    copyText(
                      doc?.endpoint || '',
                      t('monitor.integrations.customApi.endpointCopied')
                    )
                  }
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
                <CodeEditor
                  value={sampleCode}
                  mode="shell"
                  theme="monokai"
                  readOnly
                  width="100%"
                  height="300px"
                  headerOptions={{ copy: true, fullscreen: true }}
                />
              </div>
            </div>
          </div>

          <div>
            <div className="mb-3 text-lg font-semibold">
              {t('monitor.integrations.customApi.requestParamsDesc')}
            </div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-4">
              <CustomTable
                className="w-full"
                rowKey="key"
                dataSource={requestParamDocs}
                columns={requestParamColumns}
                scroll={{ x: 'max-content' }}
              />
            </div>
          </div>

          <div className="mb-[10px]">
            <div className="mb-3 text-lg font-semibold">
              {t('monitor.integrations.customApi.responseExample')}
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
              <Space direction="vertical" size={16} className="w-full">
                <div>
                  <Alert
                    message={t(
                      'monitor.integrations.customApi.successResponse'
                    )}
                    type="success"
                    showIcon={false}
                    className="rounded-b-none border-b-0"
                  />
                  <pre className="m-0 overflow-auto rounded-t-none rounded-b-md border border-t-0 border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 font-mono text-[13px] leading-relaxed">
                    {successResponse}
                  </pre>
                </div>
                <div>
                  <Alert
                    message={t('monitor.integrations.customApi.errorResponse')}
                    type="error"
                    showIcon={false}
                    className="rounded-b-none border-b-0"
                  />
                  <pre className="m-0 overflow-auto rounded-t-none rounded-b-md border border-t-0 border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 font-mono text-[13px] leading-relaxed">
                    {errorResponse}
                  </pre>
                </div>
              </Space>
            </Card>
          </div>
        </Space>
      </div>

      <ExcelImportModal ref={importRef} onSuccess={handleImport} />
      <SelectAssetModal
        ref={selectAssetRef}
        onConfirm={handleSelectAssetConfirm}
      />
      <CreateAssetModal
        ref={createAssetRef}
        onConfirm={handleCreateAssetConfirm}
      />
    </Spin>
  );
};

export default CustomApiAccess;
