'use client';

import { useEffect, useState } from 'react';
import { FileTextOutlined, UploadOutlined } from '@ant-design/icons';
import { Alert, Button, Empty, Input, Select, Upload, type UploadFile } from 'antd';

import { useRumQueries, type RumSourceMapItem } from '@/app/rum/api';
import { rumErrorMessage } from '@/app/rum/lib/error-message';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';

export default function SourceMapManager({
  application,
  releases,
  initialRelease = '',
  ciToken = '',
}: {
  application: string;
  releases: string[];
  initialRelease?: string;
  ciToken?: string;
}) {
  const { t } = useTranslation();
  const { listSourceMaps, uploadSourceMap } = useRumQueries();
  const [items, setItems] = useState<RumSourceMapItem[]>([]);
  const [release, setRelease] = useState(initialRelease);
  const [asset, setAsset] = useState('');
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    setRelease(initialRelease);
  }, [initialRelease]);

  useEffect(() => {
    if (!application) {
      setItems([]);
      return;
    }
    void listSourceMaps(application)
      .then((next) => {
        setItems(next);
        setError('');
      })
      .catch((err) => setError(rumErrorMessage(err, t)));
  }, [application, listSourceMaps, t]);

  async function submit() {
    const file = fileList[0]?.originFileObj as File | undefined;
    if (!application || !release.trim() || !asset.trim() || !file) {
      setError(t('rum.sourcemaps.required', '应用、版本、部署产物路径和文件都不能为空。'));
      return;
    }
    setUploading(true);
    setError('');
    try {
      const uploaded = await uploadSourceMap({
        application,
        release: release.trim(),
        asset: asset.trim(),
        file,
      });
      setItems((current) => [uploaded, ...current]);
      setAsset('');
      setFileList([]);
    } catch (err) {
      setError(rumErrorMessage(err, t));
    } finally {
      setUploading(false);
    }
  }

  if (!application) {
    return (
      <Empty
        description={t(
          'rum.sourcemaps.selectApplication',
          '先选择一个应用，再管理它的 SourceMap。',
        )}
      />
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <h2 className="sr-only">{t('rum.sourcemaps.title', 'SourceMap 管理')}</h2>
      {ciToken ? (
        <Alert
          type="info"
          showIcon
          message={t('rum.sourcemaps.tokenOnce', '请立即复制；此 Token 只显示一次。')}
          description={<code className="block break-all font-mono text-xs">{ciToken}</code>}
        />
      ) : null}

      {error ? <Alert type="error" showIcon message={error} /> : null}

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-fill-2)]/40 p-3">
        <div className="flex min-w-[140px] flex-1 flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-3)]">
            {t('rum.sourcemaps.release', '版本')}
          </span>
          <Select
            value={release || undefined}
            onChange={(value) => setRelease(String(value ?? ''))}
            placeholder={t('rum.sourcemaps.release', '版本')}
            options={releases.map((item) => ({ value: item, label: item }))}
            mode="tags"
            maxCount={1}
            className="w-full"
          />
        </div>
        <div className="flex min-w-[200px] flex-1 flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-3)]">
            {t('rum.sourcemaps.asset', '部署产物路径')}
          </span>
          <Input
            value={asset}
            onChange={(event) => setAsset(event.target.value)}
            placeholder="/assets/app.js"
            className="w-full font-mono"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-3)]">
            {t('rum.sourcemaps.file', 'SourceMap 文件')}
          </span>
          <Upload
            accept=".map,.gz,application/json,application/gzip"
            maxCount={1}
            beforeUpload={() => false}
            fileList={fileList}
            onChange={({ fileList: next }) => setFileList(next)}
          >
            <Button icon={<UploadOutlined aria-hidden="true" />}>
              {fileList.length > 0 ? fileList[0]?.name : t('rum.sourcemaps.file', 'SourceMap 文件')}
            </Button>
          </Upload>
        </div>
        <Button
          type="primary"
          icon={<UploadOutlined aria-hidden="true" />}
          loading={uploading}
          onClick={() => void submit()}
        >
          {t('rum.sourcemaps.upload', '上传')}
        </Button>
      </div>

      <div className="flex flex-col gap-2 pt-2">
        <div className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-3)]">
          {t('rum.sourcemaps.title', 'SourceMap 管理')} ({items.length})
        </div>
        <CustomTable<RumSourceMapItem>
          rowKey="id"
          size="middle"
          dataSource={items}
          pagination={false}
          locale={{
            emptyText: t('rum.sourcemaps.empty', '当前应用还没有上传 SourceMap。'),
          }}
          columns={[
            {
              title: t('rum.sourcemaps.release', '版本'),
              dataIndex: 'release',
              width: '25%',
              render: (value: string) => (
                <span className="inline-flex items-center gap-1.5 font-mono">
                  <FileTextOutlined className="text-[var(--color-text-3)]" />
                  {value}
                </span>
              ),
            },
            {
              title: t('rum.sourcemaps.asset', '部署产物路径'),
              dataIndex: 'fileName',
              width: '45%',
              render: (value: string) => (
                <code className="font-mono">{value}</code>
              ),
            },
            {
              title: t('rum.errors.lastSeen', '最近出现'),
              dataIndex: 'createdAt',
              width: '30%',
              render: (value: string) => (
                <span className="tabular-nums">
                  {value ? new Date(value).toLocaleString() : '—'}
                </span>
              ),
            },
          ]}
        />
      </div>
    </div>
  );
}
