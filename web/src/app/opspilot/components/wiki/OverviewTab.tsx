'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Card, Col, Descriptions, Empty, Row, Spin, Statistic } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiOverview } from '@/app/opspilot/types/wiki';
import QaTab from './QaTab';

const OverviewTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchOverview } = useWikiApi();
  const [data, setData] = useState<WikiOverview | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchOverview(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const counts = data?.counts || {};
  const contribution = data?.contribution || {};

  return (
    <Spin spinning={loading}>
      {!data && <Empty />}
      {data && (
        <>
      <Row gutter={16} className="mb-4">
        <Col span={4}>
          <Card>
            <Statistic title={t('wiki.page')} value={counts.pages || 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t('wiki.material')} value={counts.materials || 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t('wiki.buildRecord')} value={counts.build_records || 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t('wiki.check')} value={counts.open_checks || 0} />
          </Card>
        </Col>
        <Col span={4}>
          <Card>
            <Statistic title={t('wiki.relations')} value={counts.relations || 0} />
          </Card>
        </Col>
      </Row>
      <Descriptions title={t('wiki.overview')} bordered column={2} size="small">
        {Object.entries(contribution).map(([k, v]) => (
          <Descriptions.Item key={k} label={k}>
            {v}
          </Descriptions.Item>
        ))}
      </Descriptions>
        </>
      )}
      {/* 问答试用:按 spec 4.1 归属「概览」工作区 */}
      <Card title={t('wiki.qa')} className="mt-4" size="small">
        <QaTab kbId={kbId} />
      </Card>
    </Spin>
  );
};

export default OverviewTab;
