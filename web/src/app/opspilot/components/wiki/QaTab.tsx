'use client';

import React, { useState } from 'react';
import { Button, Card, Input, List, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiQaResult } from '@/app/opspilot/types/wiki';

const QaTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { qa } = useWikiApi();
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<WikiQaResult | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      setResult(await qa(kbId, query));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <Input.TextArea
          rows={2}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('wiki.ask')}
        />
        <Button type="primary" loading={loading} onClick={ask}>
          {t('wiki.ask')}
        </Button>
      </div>
      {result && (
        <Card title={t('wiki.answer')} className="mb-4">
          <p className="whitespace-pre-wrap">{result.answer}</p>
          {!!result.citations?.length && (
            <List
              size="small"
              header={t('wiki.citations')}
              dataSource={result.citations}
              renderItem={(c) => (
                <List.Item>
                  <Tag>{c.kind}</Tag>
                  {c.title}
                </List.Item>
              )}
            />
          )}
        </Card>
      )}
    </div>
  );
};

export default QaTab;
