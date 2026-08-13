'use client';

import { useEffect, useState } from 'react';
import { SpinLoading, Toast } from 'antd-mobile';
import { DownlandOutline, FileOutline } from 'antd-mobile-icons';
import { getAssetFileUrl } from './adapter';
import {
  parseAssetFiles,
  parseAssetTableColumns,
  parseAssetTableRows,
  type AssetField,
  type AssetFileMeta,
} from './model';
import { useTranslation } from '@/utils/i18n';
import styles from './assets.module.css';

function fileSizeLabel(size: number | null) {
  if (size === null || size < 0) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function AssetImagePreview({ file }: { file: AssetFileMeta }) {
  const { t } = useTranslation();
  const [src, setSrc] = useState('');
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setSrc('');
    setFailed(false);
    void getAssetFileUrl(file.fileId, false, controller.signal)
      .then((url) => {
        if (!controller.signal.aborted) setSrc(url);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [file.fileId]);

  return (
    <a
      className={styles.assetImagePreview}
      href={src || undefined}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t('assets.previewFile', undefined, { name: file.fileName })}
      aria-disabled={!src}
    >
      {src && !failed ? (
        <img src={src} alt={file.fileName} loading="lazy" decoding="async" onError={() => setFailed(true)} />
      ) : failed ? (
        <span className={styles.assetImageFallback}><FileOutline aria-hidden="true" /></span>
      ) : (
        <span className={styles.assetImageLoading}><SpinLoading style={{ '--size': '18px' }} /></span>
      )}
      <span className={styles.assetFileName}>{file.fileName}</span>
    </a>
  );
}

export default function AssetStructuredField({ field, value }: { field: AssetField; value: unknown }) {
  const { t } = useTranslation();

  if (field.type === 'table') {
    const columns = parseAssetTableColumns(field.option);
    const rows = parseAssetTableRows(value);
    if (!columns.length || !rows.length) return <span className={styles.structuredEmpty}>--</span>;
    return (
      <div className={styles.structuredTableScroll}>
        <table className={styles.structuredTable}>
          <thead><tr>{columns.map((column) => <th key={column.id}>{column.name}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => <td key={column.id}>{String(row[column.id] ?? '--')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const files = parseAssetFiles(value);
  if (!files.length) return <span className={styles.structuredEmpty}>--</span>;
  if (field.type === 'image') {
    return <div className={styles.assetImageGrid}>{files.map((file) => <AssetImagePreview file={file} key={file.fileId} />)}</div>;
  }

  const download = async (file: AssetFileMeta) => {
    try {
      const url = await getAssetFileUrl(file.fileId, true);
      if (!url) throw new Error('Missing file URL');
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.rel = 'noopener';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
    } catch {
      Toast.show({ icon: 'fail', content: t('assets.fileLoadFailed') });
    }
  };

  return (
    <div className={styles.assetFileList}>
      {files.map((file) => (
        <button
          type="button"
          className={styles.assetFileRow}
          onClick={() => void download(file)}
          aria-label={t('assets.downloadFile', undefined, { name: file.fileName })}
          key={file.fileId}
        >
          <FileOutline className={styles.assetFileIcon} aria-hidden="true" />
          <span className={styles.assetFileCopy}>
            <span className={styles.assetFileName}>{file.fileName}</span>
            {file.fileSize !== null ? <span className={styles.assetFileSize}>{fileSizeLabel(file.fileSize)}</span> : null}
          </span>
          <DownlandOutline className={styles.assetFileDownload} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
