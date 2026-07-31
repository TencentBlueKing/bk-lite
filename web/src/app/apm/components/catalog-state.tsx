'use client';

import { Empty, Result, Spin } from 'antd';
import { HandledRequestError } from '@/utils/request';

export type CatalogStateKind = 'loading' | 'empty' | 'forbidden' | 'degraded' | 'error';

interface CatalogStateProps {
  kind: CatalogStateKind;
  description?: string;
}

export function catalogErrorKind(error: unknown): Exclude<CatalogStateKind, 'loading' | 'empty'> {
  if (error instanceof HandledRequestError && error.status === 403) return 'forbidden';
  if (error instanceof HandledRequestError && error.status === 503) return 'degraded';
  return 'error';
}

export default function CatalogState({ kind, description }: CatalogStateProps) {
  if (kind === 'loading') {
    return <Spin className="my-12 flex justify-center" tip="加载 APM 数据" />;
  }
  if (kind === 'empty') {
    return <Empty description={description ?? '当前范围暂无 APM 数据'} />;
  }
  if (kind === 'forbidden') {
    return <Result status="403" title="无权访问当前组织的 APM 数据" subTitle={description} />;
  }
  if (kind === 'degraded') {
    return (
      <Result
        status="warning"
        title="遥测存储暂不可用"
        subTitle={description ?? '目录元数据仍然可用，请稍后重试遥测查询。'}
      />
    );
  }
  return <Result status="error" title="APM 数据加载失败" subTitle={description} />;
}
