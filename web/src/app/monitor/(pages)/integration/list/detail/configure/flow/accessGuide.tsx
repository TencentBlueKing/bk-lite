'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Descriptions, Spin, message } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import type { FlowProtocol } from '@/app/monitor/types/integration';
import type { FlowAssetWizardState } from './flowConfiguration';

interface FlowGuideDocument {
  protocol: FlowProtocol;
  endpoint: string;
}

interface FlowDetectResult {
  success: boolean;
  protocol: FlowProtocol;
  instance_id: string;
  last_seen_at: number | null;
  effective_sampling_rate: number;
  sampling_rate_source: string;
}

interface AccessGuideProps {
  protocol: FlowProtocol;
  objectId?: number;
  assetState: FlowAssetWizardState;
  onNext: () => void;
  onPrev: () => void;
}

const protocolLabelMap: Record<FlowProtocol, string> = {
  netflow: 'NetFlow',
  sflow: 'sFlow'
};

const AccessGuide: React.FC<AccessGuideProps> = ({
  protocol,
  objectId,
  assetState,
  onNext,
  onPrev
}) => {
  const { t } = useTranslation();
  const { getFlowGuide, detectFlowStatus } = useIntegrationApi();
  const [loading, setLoading] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [guide, setGuide] = useState<FlowGuideDocument | null>(null);
  const [detectResult, setDetectResult] = useState<FlowDetectResult | null>(null);

  useEffect(() => {
    const fetchGuide = async () => {
      if (!objectId || !assetState.cloud_region_id) {
        return;
      }
      setLoading(true);
      try {
        const result = (await getFlowGuide({
          protocol,
          cloud_region_id: assetState.cloud_region_id,
          monitor_object_id: objectId
        })) as FlowGuideDocument;
        setGuide(result);
      } catch (error: any) {
        message.error(error?.message || t('common.operationFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchGuide();
  }, [assetState.cloud_region_id, getFlowGuide, objectId, protocol, t]);

  const lastSeenAt = useMemo(() => {
    if (!detectResult?.last_seen_at) {
      return '--';
    }
    return dayjs.unix(detectResult.last_seen_at).format('YYYY-MM-DD HH:mm:ss');
  }, [detectResult?.last_seen_at]);

  const protocolLabel = protocolLabelMap[protocol];
  const endpoint = guide?.endpoint || '--';
  const guideSteps = useMemo(
    () => [
      t('monitor.integrations.flow.guideStepSelectProtocol', undefined, {
        protocol: protocolLabel
      }),
      t('monitor.integrations.flow.guideStepSetEndpoint', undefined, {
        endpoint
      }),
      t('monitor.integrations.flow.guideStepConfirmSourceIp', undefined, {
        ip: assetState.ip
      }),
      t('monitor.integrations.flow.guideStepVerifyTraffic')
    ],
    [assetState.ip, endpoint, protocolLabel, t]
  );

  const handleDetect = async () => {
    try {
      setDetecting(true);
      const result = (await detectFlowStatus({
        instance_id: assetState.instance_id,
        protocol,
        monitor_object_id: objectId!
      })) as FlowDetectResult;
      setDetectResult(result);
      if (result.success) {
        message.success(t('monitor.integrations.flow.detectSuccess'));
        setTimeout(() => {
          onNext();
        }, 800);
        return;
      }
      message.warning(t('monitor.integrations.flow.detectFailed'));
    } catch (error: any) {
      message.error(error?.message || t('common.operationFailed'));
    } finally {
      setDetecting(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <div className="px-[10px]">
        <Card title={t('monitor.integrations.flow.accessGuide')}>
          <div className="flex flex-col gap-4">
            <Alert
              showIcon
              type="info"
              message={t('monitor.integrations.flow.guideIntroTitle')}
              description={t('monitor.integrations.flow.guideIntroDesc', undefined, {
                protocol: protocolLabel
              })}
            />

            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label={t('monitor.integrations.flow.protocol')}>
                {protocolLabel}
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.flow.endpoint')}>
                <span className="break-all">{endpoint}</span>
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.flow.assetName')}>
                {assetState.name}
              </Descriptions.Item>
              <Descriptions.Item label={t('monitor.integrations.flow.assetIp')}>
                {assetState.ip}
              </Descriptions.Item>
            </Descriptions>

            <Alert
              showIcon
              type="warning"
              message={t('monitor.integrations.flow.normalizationRule')}
              description={
                <div>
                  <div>
                    {t('monitor.integrations.flow.samplingRuleDesc', undefined, {
                      protocol: protocolLabel,
                      samplingRate: assetState.fallback_sampling_rate
                    })}
                  </div>
                  <div className="mt-2">
                    {t('monitor.integrations.flow.fallbackSamplingRateDesc')}
                  </div>
                </div>
              }
            />

            <Card size="small" title={t('monitor.integrations.flow.deviceGuide')}>
              <ol className="list-decimal pl-5 space-y-2">
                {guideSteps.map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ol>
            </Card>

            <Alert
              showIcon
              type="info"
              message={t('monitor.integrations.flow.detectHintTitle')}
              description={
                <div className="space-y-1">
                  <div>{t('monitor.integrations.flow.detectHintDesc')}</div>
                  <div>{t('monitor.integrations.flow.detectHintReviewSampling')}</div>
                </div>
              }
            />

            {detectResult && (
              <Alert
                showIcon
                type={detectResult.success ? 'success' : 'warning'}
                message={
                  detectResult.success
                    ? t('monitor.integrations.flow.detectSuccess')
                    : t('monitor.integrations.flow.detectFailed')
                }
                description={
                  <div className="space-y-1">
                    <div>
                      {detectResult.success
                        ? t('monitor.integrations.flow.detectSuccessDesc')
                        : t('monitor.integrations.flow.detectFailedDesc')}
                    </div>
                    <div>
                      {t('monitor.integrations.flow.lastSeenAt')}: {lastSeenAt}
                    </div>
                    <div>
                      {t('monitor.integrations.flow.effectiveSamplingRate')}:{' '}
                      {detectResult.effective_sampling_rate}
                    </div>
                    <div>
                      {t('monitor.integrations.flow.samplingRateSource')}:{' '}
                      {detectResult.sampling_rate_source}
                    </div>
                  </div>
                }
              />
            )}

            <div className="pt-[8px] flex gap-2">
              <Button onClick={onPrev}>← {t('common.pre')}</Button>
              <Button type="primary" loading={detecting} onClick={handleDetect}>
                {t('monitor.integrations.flow.detectAccess')}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </Spin>
  );
};

export default AccessGuide;
