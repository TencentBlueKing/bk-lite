'use client';
import { useState, useMemo } from 'react';
import { Drawer, Button, Input, message, Tabs } from 'antd';
import { CopyOutlined, SendOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import useMlopsModelReleaseApi from '@/app/mlops/api/modelRelease';
import { DatasetType, ReasonParams } from '@/app/mlops/types';
import {
  REQUEST_EXAMPLES,
  RESPONSE_EXAMPLES,
  DEFAULT_TEST_BODY,
  TIP_KEYS,
  getDataFieldName,
} from '@/app/mlops/constants';
import { generateCurlExample } from '@/app/mlops/utils/common';
import servingStyle from './serving.module.scss';

const { TextArea } = Input;

interface ServingGuideDrawerProps {
  open: boolean;
  onClose: () => void;
  algorithmType: DatasetType;
  serving: {
    id: number;
    name: string;
    container_info?: {
      port?: number;
      state?: string;
    };
  } | null;
}

const ServingGuideDrawer = ({ open, onClose, algorithmType, serving }: ServingGuideDrawerProps) => {
  const { t } = useTranslation();
  const api = useMlopsModelReleaseApi();
  const [loading, setLoading] = useState(false);
  const [serverUrl, setServerUrl] = useState<string>('');
  const [requestBody, setRequestBody] = useState<string>('');
  const [response, setResponse] = useState<string>('');
  const [responseStatus, setResponseStatus] = useState<'success' | 'error' | null>(null);

  // Get configuration based on algorithm type
  const config = useMemo(() => ({
    requestExample: REQUEST_EXAMPLES[algorithmType] || REQUEST_EXAMPLES[DatasetType.ANOMALY_DETECTION],
    responseExample: RESPONSE_EXAMPLES[algorithmType] || RESPONSE_EXAMPLES[DatasetType.ANOMALY_DETECTION],
    defaultTestBody: DEFAULT_TEST_BODY[algorithmType] || DEFAULT_TEST_BODY[DatasetType.ANOMALY_DETECTION],
    tipKeys: TIP_KEYS[algorithmType] || TIP_KEYS[DatasetType.ANOMALY_DETECTION],
    dataFieldName: getDataFieldName(algorithmType),
  }), [algorithmType]);

  // Initialize request body when drawer opens or algorithm type changes
  useMemo(() => {
    setRequestBody(JSON.stringify(config.defaultTestBody, null, 2));
  }, [config.defaultTestBody]);

  const port = serving?.container_info?.port;

  // API method mapping
  const apiMethodMap: Record<DatasetType, (servingId: number, params: ReasonParams) => Promise<unknown>> = {
    [DatasetType.ANOMALY_DETECTION]: api.anomalyDetectionReason,
    [DatasetType.TIMESERIES_PREDICT]: api.timeseriesPredictReason,
    [DatasetType.LOG_CLUSTERING]: api.logClusteringReason,
    [DatasetType.CLASSIFICATION]: api.classificationReason,
    [DatasetType.IMAGE_CLASSIFICATION]: api.imageClassificationReason,
    [DatasetType.OBJECT_DETECTION]: api.objectDetectionReason,
  };

  const getRequestData = () => {
    try {
      const body = JSON.parse(requestBody);
      return body;
    } catch {
      return null;
    }
  };

  const handleTest = async () => {
    if (!serverUrl.trim()) {
      message.error(t('serving-guide.serverUrlRequired'));
      return;
    }
    const data = getRequestData();
    if (!data) {
      message.error(t('serving-guide.invalidJson'));
      return;
    }

    setLoading(true);
    setResponse('');
    setResponseStatus(null);
    try {
      const apiMethod = apiMethodMap[algorithmType];
      const result = await apiMethod(serving!.id, {
        url: serverUrl.trim(),
        ...data
      });
      setResponse(JSON.stringify(result, null, 2));
      setResponseStatus('success');
    } catch (e: unknown) {
      const errorMessage = e instanceof Error ? e.message : t('common.fetchFailed');
      setResponse(JSON.stringify({ error: errorMessage }, null, 2));
      setResponseStatus('error');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success(t('common.copySuccess'));
  };

  const externalEndpoint = `http://<${t('serving-guide.serverIp')}>:${port || '<port>'}/predict`;
  const curlExample = generateCurlExample(externalEndpoint, config.requestExample);
  const requestExample = JSON.stringify(config.requestExample, null, 2);
  const responseExample = JSON.stringify(config.responseExample, null, 2);

  const tabItems = [
    {
      key: 'usage',
      label: t('serving-guide.usageExample'),
      children: (
        <div className="pt-2">
          {/* 调用地址 */}
          <div className="pb-5 mb-5 border-b border-gray-200">
            <div className="flex items-center justify-between text-[13px] font-semibold mb-3">
              <span>{t('serving-guide.endpoint')}</span>
              <Button
                type="text"
                size="small"
                className="p-0! h-auto! text-gray-400 hover:text-blue-500!"
                icon={<CopyOutlined />}
                onClick={() => copyToClipboard(externalEndpoint)}
              />
            </div>
            <div className="flex items-center gap-2 p-2.5 bg-gray-100 rounded">
              <span className="bg-blue-500 text-white px-1.5 py-0.5 rounded text-[11px] font-semibold">POST</span>
              <code className="flex-1 font-mono text-[13px] break-all">{externalEndpoint}</code>
            </div>
            <div className="text-xs text-gray-400 mt-2">{t('serving-guide.endpointTip')}</div>
          </div>

          {/* cURL 示例 */}
          <div className="pb-5 mb-5 border-b border-gray-200">
            <div className="flex items-center justify-between text-[13px] font-semibold mb-3">
              <span>cURL {t('serving-guide.example')}</span>
              <Button
                type="text"
                size="small"
                className="p-0! h-auto! text-gray-400 hover:text-blue-500!"
                icon={<CopyOutlined />}
                onClick={() => copyToClipboard(curlExample)}
              />
            </div>
            <div className="bg-gray-100 rounded p-3 overflow-x-auto">
              <pre className="m-0 font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-break-word">{curlExample}</pre>
            </div>
          </div>

          {/* 请求格式 */}
          <div className="pb-5 mb-5 border-b border-gray-200">
            <div className="flex items-center justify-between text-[13px] font-semibold mb-3">
              <span>{t('serving-guide.requestFormat')}</span>
              <Button
                type="text"
                size="small"
                className="p-0! h-auto! text-gray-400 hover:text-blue-500!"
                icon={<CopyOutlined />}
                onClick={() => copyToClipboard(requestExample)}
              />
            </div>
            <div className="bg-gray-100 rounded p-3 overflow-x-auto">
              <pre className="m-0 font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-break-word">{requestExample}</pre>
            </div>
            <div className="text-xs text-gray-400 mt-2">{t(config.tipKeys.request)}</div>
          </div>

          {/* 响应格式 */}
          <div>
            <div className="flex items-center justify-between text-[13px] font-semibold mb-3">
              <span>{t('serving-guide.responseFormat')}</span>
            </div>
            <div className="bg-gray-100 rounded p-3 overflow-x-auto">
              <pre className="m-0 font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-break-word">{responseExample}</pre>
            </div>
            <div className="text-xs text-gray-400 mt-2">{t(config.tipKeys.response)}</div>
          </div>
        </div>
      )
    },
    {
      key: 'test',
      label: t('serving-guide.capabilityTest'),
      children: (
        <div className="pt-2">
          {/* 服务器地址 */}
          <div className="pb-5 mb-5 border-b border-gray-200">
            <div className="text-[13px] font-semibold mb-3">
              <span>{t('serving-guide.serverUrl')}</span>
              <span className="text-red-500 ml-0.5">*</span>
            </div>
            <Input
              className="font-mono! text-sm!"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder={t('serving-guide.serverUrlPlaceholder')}
            />
            <div className="text-xs text-gray-400 mt-2">{t('serving-guide.serverUrlTip')}</div>
          </div>

          {/* 请求体 */}
          <div className="pb-5 mb-5 border-b border-gray-200">
            <div className="text-[13px] font-semibold mb-3">
              <span>{t('serving-guide.requestBody')}</span>
            </div>
            <TextArea
              className="font-mono! text-xs! bg-gray-100! border-gray-200! focus:bg-white!"
              rows={10}
              value={requestBody}
              onChange={(e) => setRequestBody(e.target.value)}
              placeholder={t('serving-guide.requestBodyPlaceholder')}
            />
            <div className="text-xs text-gray-400 mt-2">{t('serving-guide.testTipNew')}</div>
          </div>

          {/* 操作区域 */}
          <div className="flex items-center gap-3 mb-4">
            <Button
              type="primary"
              icon={<SendOutlined />}
              loading={loading}
              onClick={handleTest}
              disabled={serving?.container_info?.state !== 'running'}
            >
              {t('serving-guide.sendRequest')}
            </Button>
            {serving?.container_info?.state !== 'running' && (
              <span className="text-xs text-yellow-500">{t('serving-guide.serviceNotRunning')}</span>
            )}
          </div>

          {/* 响应结果 */}
          {response && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[13px] font-semibold">{t('serving-guide.response')}</span>
                <span className={`text-[11px] px-1.5 py-0.5 rounded ${responseStatus === 'success' ? 'bg-green-50 text-green-500' : 'bg-red-50 text-red-500'}`}>
                  {responseStatus === 'success' ? 'Success' : 'Error'}
                </span>
              </div>
              <div className="bg-gray-100 rounded p-3 overflow-x-auto">
                <pre className="m-0 font-mono text-xs leading-relaxed whitespace-pre-wrap wrap-break-word">{response}</pre>
              </div>
            </div>
          )}
        </div>
      )
    }
  ];

  return (
    <Drawer
      className={`${servingStyle.content}`}
      title={`${t('serving-guide.usageExample')}`}
      width={560}
      open={open}
      onClose={onClose}
    >
      <Tabs items={tabItems} />
    </Drawer>
  );
};

export default ServingGuideDrawer;
