'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputRef,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  message
} from 'antd';
import { CopyOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { v4 as uuidv4 } from 'uuid';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import useMonitorApi from '@/app/monitor/api';
import {
  PushAccessDoc,
  PushAccessInstanceItem
} from '@/app/monitor/types/integration';
import ExcelImportModal, { ExcelImportModalRef } from './excelImportModal';
import OperateModal from '@/components/operate-modal';
import GroupTreeSelector from '@/components/group-tree-select';
import { Organization } from '@/app/monitor/types';
import { useCommon } from '@/app/monitor/context/common';
import { useUserInfoContext } from '@/context/userInfo';
import { Group } from '@/types/index';
import { useCopy } from '@/hooks/useCopy';
import CodeEditor from '@/app/monitor/components/codeEditor';

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

const buildRequestParamDocs = (doc: PushAccessDoc | null) => [
  {
    key: 'template_id',
    name: 'template_id',
    type: 'string',
    required: '是',
    description: `模板唯一标识，固定为当前模板的 template_id，例如 ${doc?.template_id || '--'}`
  },
  {
    key: 'token',
    name: 'token',
    type: 'string',
    required: '是',
    description: '所选组织对应的 API 密钥，用于鉴权'
  },
  {
    key: 'timestamp',
    name: 'timestamp',
    type: 'number',
    required: '是',
    description: '上报时间戳，支持秒、毫秒或纳秒时间戳'
  },
  {
    key: 'instances',
    name: 'instances[]',
    type: 'array',
    required: '是',
    description: '批量上报实例列表，每个实例至少包含 instance_id 和 metrics'
  },
  {
    key: 'instance_id',
    name: 'instances[].instance_id',
    type: 'string',
    required: '是',
    description: '实例唯一标识主维度，一级对象必填，二级对象也必须携带'
  },
  ...(doc?.instance_id_keys || [])
    .filter((key) => key !== 'instance_id')
    .map((key) => ({
      key: `instance_key_${key}`,
      name: `instances[].${key}`,
      type: 'string',
      required: '是',
      description: `实例联合标识维度 ${key}`
    })),
  {
    key: 'metrics',
    name: 'instances[].metrics[]',
    type: 'array',
    required: '是',
    description: '当前实例要上报的指标列表'
  },
  {
    key: 'metric_name',
    name: 'instances[].metrics[].name',
    type: 'string',
    required: '是',
    description: '指标名称，需与模板中定义的指标一致'
  },
  {
    key: 'metric_value',
    name: 'instances[].metrics[].value',
    type: 'number | string | boolean',
    required: '是',
    description: '指标值'
  },
  {
    key: 'metric_timestamp',
    name: 'instances[].metrics[].timestamp',
    type: 'number',
    required: '否',
    description: '指标级时间戳，未传时使用顶层 timestamp'
  },
  {
    key: 'metric_tags',
    name: 'instances[].metrics[].tags',
    type: 'object',
    required: '否',
    description: '附加标签字段，将透传到最终指标标签中'
  }
];

const copyText = async (text: string, successText = '复制成功') => {
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
  const assetSearchRef = useRef<InputRef>(null);
  const [createForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [doc, setDoc] = useState<PushAccessDoc | null>(null);
  const [instanceLoading, setInstanceLoading] = useState(false);
  const [instances, setInstances] = useState<PushAccessInstanceItem[]>([]);
  const [selectedOrganization, setSelectedOrganization] = useState<number>();
  const [selectedInstanceIds, setSelectedInstanceIds] = useState<React.Key[]>(
    []
  );
  const [sampleFormat, setSampleFormat] = useState<SampleFormat>('curl');
  const [apiSecret, setApiSecret] = useState('');
  const [apiSecretExists, setApiSecretExists] = useState(true);
  const [createVisible, setCreateVisible] = useState(false);
  const [selectVisible, setSelectVisible] = useState(false);
  const [assetKeyword, setAssetKeyword] = useState('');
  const [draftSelectedInstanceIds, setDraftSelectedInstanceIds] = useState<
    React.Key[]
  >([]);
  const [assetPage, setAssetPage] = useState(1);
  const [assetPageSize, setAssetPageSize] = useState(10);

  const organizationOptions = useMemo(
    () =>
      (userInfo.flatGroups || []).map((item) => ({
        value: Number(item.id),
        label: getGroupDisplayPath(item, userInfo.flatGroups || []) || item.name
      })),
    [userInfo.flatGroups]
  );

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

  useEffect(() => {
    if (!createVisible) return;
    createForm.setFieldsValue({
      name: '',
      organizations: selectedOrganization ? [selectedOrganization] : []
    });
  }, [createVisible, selectedOrganization, createForm]);

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
    if (!objectId) return;
    setInstanceLoading(true);
    try {
      const data = await getInstanceList(objectId, { page_size: -1 });
      const nextInstances = data?.results || [];
      setInstances(nextInstances);
      return nextInstances;
    } finally {
      setInstanceLoading(false);
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

  const selectableAssets = useMemo(() => {
    const keyword = assetKeyword.trim().toLowerCase();
    if (!keyword) return availableInstances;
    return availableInstances.filter((item) => {
      const name = String(item.instance_name || '').toLowerCase();
      const rawValues = Object.values(item.raw_instance || {})
        .map((value) => String(value).toLowerCase())
        .join(' ');
      return name.includes(keyword) || rawValues.includes(keyword);
    });
  }, [availableInstances, assetKeyword]);

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

  const handleCreateInstance = async () => {
    if (!selectedOrganization) return;
    const values = await createForm.validateFields();
    setSubmitting(true);
    try {
      const result = await createK8sInstance({
        organizations: values.organizations,
        id: uuidv4().replace(/-/g, ''),
        name: values.name,
        monitor_object_id: objectId
      });
      const createdInstanceId = result?.instance_id;
      const latestInstances = (await fetchInstances()) || [];
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
      message.success('资产创建成功');
      setCreateVisible(false);
      createForm.resetFields();
    } finally {
      setSubmitting(false);
    }
  };

  const requestParamDocs = useMemo(() => buildRequestParamDocs(doc), [doc]);

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

  const openSelectAssetsModal = () => {
    setDraftSelectedInstanceIds(selectedInstanceIds);
    setAssetKeyword('');
    setAssetPage(1);
    setSelectVisible(true);
  };

  useEffect(() => {
    if (!selectVisible) return;
    fetchInstances();
  }, [selectVisible]);

  const handleConfirmSelectAssets = () => {
    setSelectedInstanceIds(draftSelectedInstanceIds);
    setSelectVisible(false);
  };

  const renderOrganizationTags = (record: PushAccessInstanceItem) => {
    const orgValues = record.organization || record.organizations || [];
    if (!orgValues.length) return '--';
    return orgValues.map((item: string | number) => (
      <Tag key={`${record.instance_id}-${item}`}>
        {organizationNameMap.get(String(item)) || item}
      </Tag>
    ));
  };

  return (
    <Spin spinning={loading || submitting}>
      <div className="px-[10px]">
        <Space direction="vertical" size={20} className="w-full">
          {!apiSecretExists && (
            <Alert
              type="warning"
              showIcon
              message="当前组织未配置系统管理 API 密钥，请先前往系统管理创建。"
            />
          )}

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
                <Form.Item label="组织" required>
                  <div className="w-1/2 max-w-full">
                    <Select
                      value={selectedOrganization}
                      placeholder="请选择组织"
                      options={organizationOptions}
                      onChange={(value) => setSelectedOrganization(value)}
                    />
                  </div>
                </Form.Item>

                <Form.Item label="API 密钥" required>
                  <div className="flex w-full items-center gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3 py-2">
                    <span className="shrink-0 text-[13px] text-[var(--color-primary)]">
                      Token
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
                      复制
                    </Button>
                  </div>
                </Form.Item>

                <Form.Item label="监控资产" required className="mb-0">
                  <Space direction="vertical" size={16} className="w-full">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Button
                          icon={<PlusOutlined />}
                          type="primary"
                          onClick={() => setCreateVisible(true)}
                        >
                          新建资产
                        </Button>
                        <Button
                          icon={<PlusOutlined />}
                          onClick={openSelectAssetsModal}
                        >
                          选择已有资产
                        </Button>
                        {selectedAssets.length > 0 && (
                          <span className="text-[var(--color-text-3)]">
                            已选择 {selectedAssets.length}{' '}
                            个资产，将作为同一批次监控数据上报
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
                                  label: '实例名称',
                                  required: true
                                }
                              ],
                              groupList: organizationList.current
                            })
                          }
                        >
                          导入新资产
                        </Button>
                        <Button
                          onClick={() => setSelectedInstanceIds([])}
                          disabled={!selectedInstanceIds.length}
                        >
                          清空选择
                        </Button>
                      </div>
                    </div>

                    {selectedAssets.length ? (
                      <Table
                        rowKey="instance_id"
                        pagination={false}
                        dataSource={selectedAssets}
                        columns={[
                          {
                            title: '资产名称',
                            dataIndex: 'instance_name',
                            key: 'instance_name'
                          },
                          {
                            title: '资产ID',
                            dataIndex: 'instance_id',
                            key: 'instance_id',
                            render: (_, record) => (
                              <span className="font-mono text-[13px] text-[var(--color-text-1)]">
                                {buildInstanceIdentityLabel(
                                  record,
                                  doc?.instance_id_keys || ['instance_id']
                                )}
                              </span>
                            )
                          },
                          {
                            title: '所属组织',
                            dataIndex: 'organization',
                            key: 'organization',
                            render: (_, record) =>
                              renderOrganizationTags(record)
                          },
                          {
                            title: '操作',
                            key: 'action',
                            width: 80,
                            render: (_, record) => (
                              <Button
                                type="link"
                                className="px-0"
                                onClick={() =>
                                  setSelectedInstanceIds((prev) =>
                                    prev.filter(
                                      (id) => id !== record.instance_id
                                    )
                                  )
                                }
                              >
                                移除
                              </Button>
                            )
                          }
                        ]}
                      />
                    ) : (
                      <div
                        className="flex items-center justify-center"
                        style={{ minHeight: '240px' }}
                      >
                        <Empty description="请选择或创建监控资产" />
                      </div>
                    )}
                  </Space>
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
                  onClick={() =>
                    copyText(doc?.endpoint || '', 'API 端点已复制')
                  }
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

          <div className="mb-[10px]">
            <div className="mb-3 text-lg font-semibold">响应示例</div>
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
                    message="成功响应 (200)"
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
                    message="错误响应 (401)"
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
      <OperateModal
        open={selectVisible}
        width={900}
        title="选择接入资产"
        onCancel={() => setSelectVisible(false)}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              onClick={handleConfirmSelectAssets}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={() => setSelectVisible(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        }
      >
        <Space direction="vertical" size={16} className="w-full">
          <p className="mb-0 text-[var(--color-text-3)]">
            仅展示所属组织包含当前组织的资产。确认后，请求示例会自动按所选资产生成批量上报
            payload。
          </p>
          <Input
            ref={assetSearchRef}
            placeholder="按实例名称或实例 ID 搜索"
            value={assetKeyword}
            onChange={(e) => setAssetKeyword(e.target.value)}
          />
          <Table
            rowKey="instance_id"
            loading={instanceLoading}
            dataSource={selectableAssets}
            scroll={{ x: 760, y: 420 }}
            pagination={{
              current: assetPage,
              pageSize: assetPageSize,
              total: selectableAssets.length,
              showSizeChanger: true,
              pageSizeOptions: ['10', '20', '50'],
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => {
                setAssetPage(page);
                setAssetPageSize(pageSize);
              }
            }}
            rowSelection={{
              selectedRowKeys: draftSelectedInstanceIds,
              onChange: (keys) => setDraftSelectedInstanceIds(keys)
            }}
            columns={[
              {
                title: '资产名称',
                dataIndex: 'instance_name',
                key: 'instance_name',
                width: 260,
                ellipsis: false,
                render: (value) => value || '--'
              },
              {
                title: '实例标识',
                dataIndex: 'instance_id',
                key: 'instance_id',
                width: 260,
                render: (_, record) => (
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 font-mono text-[13px] text-[var(--color-text-1)]">
                      {buildInstanceIdentityLabel(
                        record,
                        doc?.instance_id_keys || ['instance_id']
                      )}
                    </span>
                    <Button
                      type="link"
                      size="small"
                      className="px-0"
                      onClick={() =>
                        copy(
                          buildInstanceIdentityLabel(
                            record,
                            doc?.instance_id_keys || ['instance_id']
                          )
                        )
                      }
                    >
                      复制
                    </Button>
                  </div>
                )
              },
              {
                title: '所属组织',
                dataIndex: 'organization',
                key: 'organization',
                width: 220,
                render: (_, record) => renderOrganizationTags(record)
              }
            ]}
          />
        </Space>
      </OperateModal>

      <OperateModal
        open={createVisible}
        title="新建资产"
        onCancel={() => setCreateVisible(false)}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={submitting}
              onClick={handleCreateInstance}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={() => setCreateVisible(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        }
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            label="实例名称"
            name="name"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Input placeholder="请输入实例名称" />
          </Form.Item>
          <Form.Item
            label="所属组织"
            name="organizations"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <GroupTreeSelector />
          </Form.Item>
        </Form>
      </OperateModal>
    </Spin>
  );
};

export default CustomApiAccess;
