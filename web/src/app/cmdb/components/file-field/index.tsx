'use client';

/**
 * CMDB 附件/图片字段组件（企业版）。
 *
 * - FileFieldUpload：实例新增/编辑表单中的上传控件（受 antd Form 控制，value/onChange）。
 * - FileFieldDisplay：详情页只读展示（附件文件名列表+下载；图片缩略图+文件名+放大预览）。
 * - FileFieldCell：列表摘要（附件首个文件名+数量；图片首张缩略图）。
 *
 * 后端字段值为元数据 JSON 字符串数组：[{ file_id, file_name, ... }]。
 * 下载/预览：后端 download_file 返回预签名 URL（JSON），前端经 axios（带令牌）取回后
 * 直接用于 <img src>/下载——绕开「直链请求不带令牌」的鉴权问题（请提供令牌）。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
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

const metaToUploadFile = (m: FileMeta): UploadFile => ({
  uid: m.file_id,
  name: m.file_name,
  status: 'done',
});

// ---------------------------------------------------------------- 鉴权直链

/** 经鉴权接口（axios 带令牌）取预签名 URL 后渲染 antd Image，支持放大预览。 */
const AuthedImage: React.FC<{
  fileId: string;
  alt?: string;
  width?: number;
  height?: number;
  preview?: boolean;
}> = ({ fileId, alt, width = 64, height = 64, preview = true }) => {
  const instanceApi = useInstanceApi();
  const apiRef = useRef(instanceApi);
  apiRef.current = instanceApi;
  const [src, setSrc] = useState<string>('');

  useEffect(() => {
    let alive = true;
    apiRef.current
      .getFileUrl(fileId)
      .then((r) => {
        if (alive) setSrc(r?.url || '');
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [fileId]);

  if (!src) {
    return (
      <div
        style={{ width, height, borderRadius: 4, background: 'var(--color-fill-2, #f0f0f0)' }}
      />
    );
  }
  return (
    <Image
      src={src}
      alt={alt}
      width={width}
      height={height}
      preview={preview}
      style={{ objectFit: 'cover', borderRadius: 4 }}
    />
  );
};

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

  const onPreview = async (file: UploadFile) => {
    try {
      const r = await instanceApi.getFileUrl(String(file.uid));
      if (r?.url) window.open(r.url, '_blank', 'noopener');
    } catch {
      // ignore
    }
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
  const instanceApi = useInstanceApi();
  const metas = useMemo(() => parseFileValue(value), [value]);
  if (!metas.length) return <>--</>;

  const openFile = async (fileId: string) => {
    try {
      const r = await instanceApi.getFileUrl(fileId);
      if (r?.url) window.open(r.url, '_blank', 'noopener');
    } catch {
      // ignore
    }
  };

  if (fieldType === 'image') {
    return (
      <Image.PreviewGroup>
        <div className="flex flex-wrap gap-3">
          {metas.map((m) => (
            <div
              key={m.file_id}
              className="flex flex-col items-center gap-1"
              style={{ width: 72 }}
            >
              <AuthedImage fileId={m.file_id} alt={m.file_name} width={64} height={64} />
              <span
                className="block w-full text-center text-[12px] text-[var(--color-text-3)] truncate"
                title={m.file_name}
              >
                {m.file_name}
              </span>
            </div>
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
          onClick={() => openFile(m.file_id)}
          className="inline-flex items-center gap-1 cursor-pointer"
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
      <div
        className="flex items-center gap-1"
        onClick={(e) => e.stopPropagation()}
        title={metas.map((m) => m.file_name).join('\n')}
      >
        <AuthedImage fileId={metas[0].file_id} alt={metas[0].file_name} width={28} height={28} preview={false} />
        {metas.length > 1 && (
          <span className="text-[12px] text-[var(--color-text-3)]">+{metas.length - 1}</span>
        )}
      </div>
    );
  }

  // 附件：列表展示首个文件名 + 数量
  return (
    <span
      className="inline-flex items-center gap-1 max-w-[220px]"
      title={metas.map((m) => m.file_name).join('\n')}
    >
      <PaperClipOutlined />
      <span className="truncate">{metas[0].file_name}</span>
      {metas.length > 1 && (
        <span className="text-[12px] text-[var(--color-text-3)]">+{metas.length - 1}</span>
      )}
    </span>
  );
};
