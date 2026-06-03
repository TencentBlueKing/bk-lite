import React, { useMemo } from 'react';
import ComTable from '../comTable';

/**
 * 将多查询 rawData（keyed object）合并为 ComTable 所需的行数组。
 * 支持三种合并策略：
 * - detail + total  → 高频 URL Top10（计算 req_ratio）
 * - base + p95      → 慢请求 URL Top10（按 url.path join，按 p95 排序取 top10）
 * - errors + status → 错误请求 URL Top10（按 url.path join，取 primary_status_code）
 * 单查询模式直接透传。
 */
const mergeMultiQueryData = (rawData: any): any[] => {
  if (Array.isArray(rawData)) return rawData;
  if (!rawData || typeof rawData !== 'object') return [];

  // 高频 URL Top10: detail + total
  if (rawData.detail && rawData.total) {
    const totalRow = Array.isArray(rawData.total) ? rawData.total[0] : null;
    const totalReqcount = totalRow
      ? Number(totalRow.total_reqcount || 0)
      : 0;
    return (rawData.detail as any[]).map((row) => {
      const reqcount = Number(row.reqcount || 0);
      return {
        ...row,
        req_ratio: totalReqcount > 0 ? (reqcount / totalReqcount) * 100 : 0
      };
    });
  }

  // 慢请求 URL Top10: base + p95
  if (rawData.base && rawData.p95) {
    const p95Map = new Map<string, Record<string, unknown>>();
    for (const row of rawData.p95 as any[]) {
      const path = String(row['url.path'] ?? '');
      if (path) p95Map.set(path, row);
    }
    const merged = (rawData.base as any[]).map((row) => {
      const path = String(row['url.path'] ?? '');
      const p95Row = p95Map.get(path);
      return {
        ...row,
        p95_duration: p95Row ? p95Row.p95_duration : undefined
      };
    });
    // 按 p95_duration 降序排序，取 top 10
    merged.sort(
      (a, b) => Number(b.p95_duration || 0) - Number(a.p95_duration || 0)
    );
    return merged.slice(0, 10);
  }

  // 错误请求 URL Top10: errors + status
  if (rawData.errors && rawData.status) {
    // 从 status 结果中，为每个 url.path 取出现次数最多的 status_code
    const statusMap = new Map<string, string>();
    for (const row of rawData.status as any[]) {
      const path = String(row['url.path'] ?? '');
      if (path && !statusMap.has(path)) {
        // status 结果已按 status_count desc 排序，第一条即为该 path 的主要状态码
        statusMap.set(path, String(row['http.response.status_code'] ?? ''));
      }
    }
    return (rawData.errors as any[]).map((row) => {
      const path = String(row['url.path'] ?? '');
      return {
        ...row,
        primary_status_code: statusMap.get(path) ?? ''
      };
    });
  }

  return [];
};

const HttpRequestTable: React.FC<any> = ({ rawData, ...rest }) => {
  const normalizedData = useMemo(() => mergeMultiQueryData(rawData), [rawData]);
  return <ComTable {...rest} rawData={normalizedData} />;
};

export default HttpRequestTable;
