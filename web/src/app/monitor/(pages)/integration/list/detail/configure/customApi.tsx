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
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message
} from 'antd';
import {
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  UploadOutlined
} from '@ant-design/icons';
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

type SampleFormat = 'curl' | 'python' | 'javascript';

const formatJson = (value: Record<string, any>) => JSON.stringify(value, null, 2);

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
  ...((doc?.instance_id_keys || [])
    .filter((key) => key !== 'instance_id')
    .map((key) => ({
      key: `instance_key_${key}`,
      name: `instances[].${key}`,
      type: 'string',
      required: '是',
      description: `实例联合标识维度 ${key}`
    }))),
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
  return keys
    .map((key) => rawInstance[key] || '--')
    .join(' / ');
};

const CustomApiAccess: React.FC = () => {
  const { t } = useTranslation();
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
  const [selectedInstanceIds, setSelectedInstanceIds] = useState<React.Key[]>([]);
  const [sampleFormat, setSampleFormat] = useState<SampleFormat>('curl');
  const [apiSecret, setApiSecret] = useState('');
  const [apiSecretExists, setApiSecretExists] = useState(true);
  const [createVisible, setCreateVisible] = useState(false);
  const [selectVisible, setSelectVisible] = useState(false);
  const [assetKeyword, setAssetKeyword] = useState('');
  const [draftSelectedInstanceIds, setDraftSelectedInstanceIds] = useState<React.Key[]>([]);
  const [assetPage, setAssetPage] = useState(1);
  const [assetPageSize, setAssetPageSize] = useState(10);

  const organizationOptions = useMemo(
    () =>
      (userInfo.flatGroups || []).map((item) => ({
        value: Number(item.id),
        label: item.path || item.name
      })),
    [userInfo.flatGroups]
  );

  const organizationNameMap = useMemo(
    () =>
      new Map(
        (userInfo.flatGroups || []).map((item) => [
          String(item.id),
          item.path || item.name || String(item.id)
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
      const data = await getPushAccessDoc(pluginId, team ? { team } : undefined);
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
    const normalizedInstance = instanceIdKeys.reduce<Record<string, any>>((acc, key) => {
      acc[key] =
        selectedRawInstance[key] || sourceInstance[key] || (key === 'instance_id' ? 'demo-instance-id' : `demo-${key}`);
      return acc;
    }, {});

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
    const endpoint = doc?.endpoint || '/api/v1/monitor/open_api/push_api/report/';
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

  const renderCodeBlock = (
    title: string,
    content: string,
    tone: 'default' | 'error' = 'default'
  ) => (
    <div className="overflow-hidden rounded-md border border-[var(--color-border)] bg-[#111827]">
      <div className="flex items-center justify-between border-b border-[#1f2937] px-[12px] py-[10px]">
        <Typography.Text className="text-[13px] font-medium text-[#e5e7eb]">
          {title}
        </Typography.Text>
        <Button
          type="text"
          size="small"
          icon={<CopyOutlined />}
          className="!text-[#cbd5e1] hover:!text-white"
          onClick={() => copyText(content, `${title}已复制`)}
        >
          复制
        </Button>
      </div>
      <pre
        className={`overflow-auto p-[16px] text-[13px] leading-[1.7] ${
          tone === 'error' ? 'text-[#fca5a5]' : 'text-[#e5e7eb]'
        }`}
      >
        <code>{content}</code>
      </pre>
    </div>
  );

  const openSelectAssetsModal = () => {
    setDraftSelectedInstanceIds(selectedInstanceIds);
    setAssetKeyword('');
    setAssetPage(1);
    setSelectVisible(true);
  };

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
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">接入配置</b>
            <Card>
              <Space direction="vertical" size={16} className="w-full">
              <Form layout="vertical">
                <Form.Item label="组织">
                  <div className="flex items-start gap-4">
                    <div className="w-[320px]">
                      <Select
                        value={selectedOrganization}
                        placeholder="请选择组织"
                        options={organizationOptions}
                        onChange={(value) => setSelectedOrganization(value)}
                      />
                    </div>
                  </div>
                </Form.Item>

                <Form.Item label="API 密钥">
                  <div className="flex items-start gap-4">
                    <div className="w-[560px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] px-[14px] py-[12px] shadow-sm">
                      <div className="flex items-center justify-between gap-[12px]">
                        <div className="flex min-w-0 items-center gap-[10px]">
                          <span className="rounded-md bg-[var(--color-fill-2)] px-[8px] py-[2px] text-[12px] text-[var(--color-text-2)]">
                            Token
                          </span>
                        <Typography.Text
                          className="min-w-0 flex-1 truncate font-mono text-[13px] leading-[1.7] text-[var(--color-text-1)]"
                          title={apiSecret || '--'}
                        >
                          {apiSecret || '--'}
                        </Typography.Text>
                        </div>
                        <Button
                          type="default"
                          size="small"
                          icon={<CopyOutlined />}
                          className="shrink-0"
                          disabled={!apiSecret}
                          onClick={() => copyText(apiSecret, 'API 密钥已复制')}
                        >
                          复制
                        </Button>
                      </div>
                    </div>
                  </div>
                </Form.Item>
              </Form>
              <div>
                <div className="flex items-center justify-between mb-[10px]">
                  <span className="text-[14px]">
                    监控资产
                    <span
                      className="text-[#ff4d4f] align-middle text-[14px] ml-[4px]"
                      style={{ fontFamily: 'SimSun, sans-serif' }}
                    >
                      *
                    </span>
                  </span>
                  <div className="flex gap-[8px]">
                    <Button
                      icon={<PlusOutlined />}
                      type="primary"
                      onClick={() => setCreateVisible(true)}
                    >
                      新建资产
                    </Button>
                    <Button onClick={openSelectAssetsModal}>选择已有资产</Button>
                    <Button
                      icon={<UploadOutlined />}
                      onClick={() =>
                        importRef.current?.showModal({
                          title: t('common.import'),
                          columns: [
                            { name: 'id', label: 'ID', required: true, is_only: true },
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
                      导入
                    </Button>
                    <Button
                      icon={<DeleteOutlined />}
                      onClick={() => setSelectedInstanceIds([])}
                      disabled={!selectedInstanceIds.length}
                    >
                      清空
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
                        title: '实例名称',
                        dataIndex: 'instance_name',
                        key: 'instance_name'
                      },
                      {
                        title: '实例标识',
                        dataIndex: 'instance_id',
                        key: 'instance_id',
                        render: (_, record) => (
                          <Typography.Text copyable>
                            {buildInstanceIdentityLabel(record, doc?.instance_id_keys || ['instance_id'])}
                          </Typography.Text>
                        )
                      },
                      {
                        title: '组织',
                        dataIndex: 'organization',
                        key: 'organization',
                        render: (_, record) => renderOrganizationTags(record)
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
              </div>
              </Space>
            </Card>
          </div>

          <div>
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">API 端点</b>
            <Card>
              <div className="flex items-center justify-between rounded-[14px] border border-[var(--color-border)] bg-[var(--color-fill-1)] px-[16px] py-[14px]">
                <Typography.Text className="font-mono text-[13px]">
                  {doc?.endpoint || '--'}
                </Typography.Text>
                <Button
                  type="text"
                  icon={<CopyOutlined />}
                  disabled={!doc?.endpoint}
                  onClick={() => copyText(doc?.endpoint || '', 'API 端点已复制')}
                >
                  复制
                </Button>
              </div>
            </Card>
          </div>

          <div>
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">请求示例</b>
            <Card>
              <Space direction="vertical" size={16} className="w-full">
                <Segmented
                  value={sampleFormat}
                  options={[
                    { label: 'cURL', value: 'curl' },
                    { label: 'Python', value: 'python' },
                    { label: 'JavaScript', value: 'javascript' }
                  ]}
                  onChange={(value) => setSampleFormat(value as SampleFormat)}
                />
                {renderCodeBlock('请求示例', sampleCode)}
              </Space>
            </Card>
          </div>

          <div>
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">请求参数说明</b>
            <Card>
              <Table
                rowKey="key"
                pagination={false}
                dataSource={requestParamDocs}
                columns={[
                  { title: '参数', dataIndex: 'name', key: 'name' },
                  { title: '类型', dataIndex: 'type', key: 'type' },
                  { title: '必填', dataIndex: 'required', key: 'required' },
                  { title: '说明', dataIndex: 'description', key: 'description' }
                ]}
              />
            </Card>
          </div>

          <div>
            <b className="text-[14px] flex mb-[10px] ml-[-10px]">响应格式</b>
            <Card>
              <Space direction="vertical" size={16} className="w-full">
                <div>
                  <Typography.Title level={5}>成功响应</Typography.Title>
                  {renderCodeBlock('成功响应 (200)', successResponse)}
                </div>
                <div>
                  <Typography.Title level={5}>错误响应</Typography.Title>
                  {renderCodeBlock('错误响应 (401)', errorResponse, 'error')}
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
            <Button className="mr-[10px]" type="primary" onClick={handleConfirmSelectAssets}>
              {t('common.confirm')}
            </Button>
            <Button onClick={() => setSelectVisible(false)}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Space direction="vertical" size={16} className="w-full">
          <Typography.Paragraph type="secondary" className="!mb-0">
            仅展示所属组织包含当前组织的资产。确认后，请求示例会自动按所选资产生成批量上报 payload。
          </Typography.Paragraph>
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
                  <Typography.Text copyable className="font-mono text-[13px]">
                    {buildInstanceIdentityLabel(record, doc?.instance_id_keys || ['instance_id'])}
                  </Typography.Text>
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
            <Button onClick={() => setCreateVisible(false)}>{t('common.cancel')}</Button>
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
