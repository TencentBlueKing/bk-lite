'use client';

/**
 * CMDB 附件/图片字段组件（企业版）。
 *
 * - FileFieldUpload：实例新增/编辑表单中的上传控件（受 antd Form 控制，value/onChange）。
 * - FileFieldDisplay：详情页只读展示（附件文件名列表+下载；图片缩略图+放大预览）。
 * - FileFieldCell：列表摘要（附件文件数；图片首张缩略图）。
 *
 * 后端把字段值存为元数据 JSON 字符串数组：
 *   [{ file_id, file_name, file_size, mime_type, object_key, upload_time, uploader }]
 * 上传走后端校验（预上传），保存时提交引用；下载经后端校权后 302 跳预签名 URL。
 */

import React, { useMemo, useRef, useState } from 'react';
import { Upload, Image, Button, message } from 'antd';
import { UploadOutlined, PaperClipOutlined, DownloadOutlined } from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useTranslation } from '@/utils/i18n';

export type FileFieldType = 'attachment' | 'image';

export interface FileMeta {
  file_id: string;
  file_name: string;
  file_size?: number;
  mime_type?: string;
  object_key?: string;
  upload_time?: string;
  uploader?: string;
}

const MB = 1024 * 1024;

// 系统级约束（与后端 enterprise/instance_ops/constants.py 保持一致；后端为最终兜底）
export const FILE_FIELD_LIMITS: Record<FileFieldType, { maxCount: number; maxSize: number; accept: string }> = {
  attachment: {
    maxCount: 5,
    maxSize: 50 * MB,
    accept: '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.md,.rtf,.zip,.rar,.7z,.gz,.tar,.jpg,.jpeg,.png,.gif,.webp,.bmp',
  },
  image: {
    maxCount: 5,
    maxSize: 10 * MB,
    accept: '.jpg,.jpeg,.png,.gif,.webp,.bmp',
  },
};

/** 把后端字段值（JSON 字符串 / 数组）解析为元数据列表。 */
export const parseFileValue = (value: any): FileMeta[] => {
  if (!value) return [];
  let raw = value;
  if (typeof raw === 'string') {
    try {
      raw = JSON.parse(raw);
    } catch {
      return [];
    }
  }
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item: any) =>
      typeof item === 'string'
        ? ({ file_id: item, file_name: item } as FileMeta)
        : (item as FileMeta)
    )
    .filter((m: FileMeta) => m && m.file_id);
};

/** 浏览器直链下载/预览（经代理，后端校权后 302 跳预签名 URL）。 */
export const fileDownloadUrl = (fileId: string): string =>
  `/api/proxy/cmdb/api/instance/download_file/${fileId}/`;

const metaToUploadFile = (m: FileMeta): UploadFile => ({
  uid: m.file_id,
  name: m.file_name,
  status: 'done',
  url: fileDownloadUrl(m.file_id),
  thumbUrl: fileDownloadUrl(m.file_id),
});

// ---------------------------------------------------------------- 上传控件

interface FileFieldUploadProps {
  value?: any;
  onChange?: (value: FileMeta[]) => void;
  modelId: string;
  attrId: string;
  fieldType: FileFieldType;
  disabled?: boolean;
}

export const FileFieldUpload: React.FC<FileFieldUploadProps> = ({
  value,
  onChange,
  modelId,
  attrId,
  fieldType,
  disabled,
}) => {
  const { t } = useTranslation();
  const instanceApi = useInstanceApi();
  const limits = FILE_FIELD_LIMITS[fieldType];

  const [fileList, setFileList] = useState<UploadFile[]>(() =>
    parseFileValue(value).map(metaToUploadFile)
  );
  // 本会话内上传（尚未提交）的文件 id，移除时清理临时文件
  const sessionUploaded = useRef<Set<string>>(new Set());

  const emitChange = (list: UploadFile[]) => {
    const metas: FileMeta[] = list
      .filter((f) => f.status === 'done')
      .map((f) => ({ file_id: String(f.uid), file_name: f.name }));
    onChange?.(metas);
  };

  const beforeUpload: UploadProps['beforeUpload'] = (file) => {
    if (fileList.length >= limits.maxCount) {
      message.error(
        t('fileFieldMaxCount', undefined, { count: limits.maxCount })
      );
      return Upload.LIST_IGNORE;
    }
    if (file.size > limits.maxSize) {
      message.error(
        t('fileFieldTooLarge', undefined, { size: Math.floor(limits.maxSize / MB) })
      );
      return Upload.LIST_IGNORE;
    }
    return true;
  };

  const customRequest: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options;
    const formData = new FormData();
    formData.append('file', file as Blob);
    formData.append('model_id', modelId);
    formData.append('attr_id', attrId);
    try {
      const meta: FileMeta = await instanceApi.uploadFile(formData);
      sessionUploaded.current.add(meta.file_id);
      setFileList((prev) => {
        const next = [...prev, metaToUploadFile(meta)];
        emitChange(next);
        return next;
      });
      onSuccess?.(meta as any);
    } catch (err) {
      onError?.(err as any);
    }
  };

  const handleRemove = (file: UploadFile) => {
    const fileId = String(file.uid);
    // 仅清理本会话上传、尚未提交的临时文件；已提交文件在保存实例时由后端回收
    if (sessionUploaded.current.has(fileId)) {
      instanceApi.deleteFile(fileId).catch(() => undefined);
      sessionUploaded.current.delete(fileId);
    }
    setFileList((prev) => {
      const next = prev.filter((f) => f.uid !== file.uid);
      emitChange(next);
      return next;
    });
    return true;
  };

  const onPreview = (file: UploadFile) => {
    window.open(file.url || fileDownloadUrl(String(file.uid)), '_blank');
  };

  const reachedMax = fileList.length >= limits.maxCount;

  return (
    <Upload
      accept={limits.accept}
      listType={fieldType === 'image' ? 'picture-card' : 'text'}
      fileList={fileList}
      disabled={disabled}
      multiple
      beforeUpload={beforeUpload}
      customRequest={customRequest}
      onRemove={handleRemove}
      onPreview={onPreview}
    >
      {!reachedMax &&
        !disabled &&
        (fieldType === 'image' ? (
          <div>
            <UploadOutlined />
            <div className="mt-1">{t('fileFieldUpload')}</div>
          </div>
        ) : (
          <Button icon={<UploadOutlined />}>{t('fileFieldUpload')}</Button>
        ))}
    </Upload>
  );
};

// ---------------------------------------------------------------- 只读展示（详情页）

interface FileFieldDisplayProps {
  value?: any;
  fieldType: FileFieldType;
}

export const FileFieldDisplay: React.FC<FileFieldDisplayProps> = ({ value, fieldType }) => {
  const metas = useMemo(() => parseFileValue(value), [value]);
  if (!metas.length) return <>--</>;

  if (fieldType === 'image') {
    return (
      <Image.PreviewGroup>
        <div className="flex flex-wrap gap-2">
          {metas.map((m) => (
            <Image
              key={m.file_id}
              src={fileDownloadUrl(m.file_id)}
              alt={m.file_name}
              width={64}
              height={64}
              style={{ objectFit: 'cover', borderRadius: 4 }}
            />
          ))}
        </div>
      </Image.PreviewGroup>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {metas.map((m) => (
        <a
          key={m.file_id}
          href={fileDownloadUrl(m.file_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1"
        >
          <PaperClipOutlined />
          <span>{m.file_name}</span>
          <DownloadOutlined />
        </a>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------- 列表摘要

interface FileFieldCellProps {
  value?: any;
  fieldType: FileFieldType;
}

export const FileFieldCell: React.FC<FileFieldCellProps> = ({ value, fieldType }) => {
  const metas = useMemo(() => parseFileValue(value), [value]);
  if (!metas.length) return <>--</>;

  if (fieldType === 'image') {
    return (
      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <Image
          src={fileDownloadUrl(metas[0].file_id)}
          alt={metas[0].file_name}
          width={28}
          height={28}
          style={{ objectFit: 'cover', borderRadius: 4 }}
        />
        {metas.length > 1 && <span className="text-[12px] text-[var(--color-text-3)]">+{metas.length - 1}</span>}
      </div>
    );
  }

  return (
    <span className="inline-flex items-center gap-1">
      <PaperClipOutlined />
      {metas.length}
    </span>
  );
};
