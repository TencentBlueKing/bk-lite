import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import ConfigAnalysisReportCard from '../src/app/opspilot/components/custom-chat-sse/ConfigAnalysisReportCard';

const problematicHtml = renderToStaticMarkup(
  <ConfigAnalysisReportCard
    report={{
      report_id: 'report-1',
      title: '配置检查报告',
      cluster_name: 'Kubernetes - 1',
      scope: {
        cluster_name: 'Kubernetes - 1',
        namespace: 'payments',
        instance_name: 'prod-cluster',
        name: 'gateway',
      },
      summary: {
        total: 36,
        problematic: 32,
        healthy: 4,
        top_recommendation: '优先补齐高危问题对应的探针与资源限制配置',
      },
      severity_sections: [
        {
          severity: 'high',
          title: 'High',
          issues: [
            {
              issue: '未配置存活探针',
              count: 10,
              workloads: ['gateway (opspilot-check-a)', 'analytics (opspilot-check-b)'],
              risk: '容器异常时无法被及时发现并自愈',
            },
          ],
        },
      ],
      recommendations: [
        {
          priority: 'P1',
          action: '补齐 liveness / readiness probe',
          target: 'gateway / analytics',
          benefit: '提高发布稳定性与故障自愈能力',
        },
      ],
      markdown: '# fallback',
      fallback_markdown: '# fallback',
      received_at: Date.now(),
    }}
  />
);

assert.match(problematicHtml, /配置检查报告/);
assert.match(problematicHtml, /<table/);
assert.match(problematicHtml, /未配置存活探针/);
assert.match(problematicHtml, /补齐 liveness \/ readiness probe/);
assert.match(problematicHtml, /实例：prod-cluster/);
assert.match(problematicHtml, /对象：gateway/);

const healthyHtml = renderToStaticMarkup(
  <ConfigAnalysisReportCard
    report={{
      report_id: 'report-2',
      title: '配置检查报告',
      cluster_name: 'Kubernetes - 1',
      scope: {
        cluster_name: 'Kubernetes - 1',
        namespace: 'default',
        instance_name: 'staging-cluster',
        target_name: 'payments-api',
      },
      scan_range: {
        offset: 25,
        limit: 25,
        has_more: true,
      },
      summary: {
        total: 8,
        problematic: 0,
        healthy: 8,
        top_recommendation: '当前无需额外修复动作',
      },
      severity_sections: [],
      recommendations: [],
      markdown: '# fallback',
      fallback_markdown: '# fallback',
      received_at: Date.now(),
    }}
  />
);

assert.match(healthyHtml, /未发现明显配置问题/);
assert.equal(healthyHtml.includes('问题类别'), false);
assert.match(healthyHtml, /当前展示第 26 - 50 项结果，仍有更多对象待继续检查/);
assert.match(healthyHtml, /实例：staging-cluster/);
assert.match(healthyHtml, /对象：payments-api/);

const healthyNoRecommendationHtml = renderToStaticMarkup(
  <ConfigAnalysisReportCard
    report={{
      report_id: 'report-3',
      title: '配置检查报告',
      cluster_name: 'Kubernetes - 1',
      summary: {
        total: 12,
        problematic: 0,
        healthy: 12,
      },
      severity_sections: [],
      recommendations: [],
      markdown: '# fallback',
      fallback_markdown: '# fallback',
      received_at: Date.now(),
    }}
  />
);

assert.match(healthyNoRecommendationHtml, /当前扫描结果未发现明显风险，暂无额外修复建议/);
assert.equal(healthyNoRecommendationHtml.includes('建议优先处理高风险配置项'), false);

const degradedHtml = renderToStaticMarkup(
  <ConfigAnalysisReportCard
    report={{
      report_id: 'report-4',
      title: '配置检查报告',
      cluster_name: 'Kubernetes - 1',
      summary: {
        total: 18,
        problematic: 6,
        healthy: 12,
      },
      severity_sections: [],
      recommendations: [],
      markdown: '# fallback',
      fallback_markdown: '# fallback',
      received_at: Date.now(),
    }}
  />
);

assert.match(degradedHtml, /已发现配置问题，但明细暂不可用/);
assert.equal(degradedHtml.includes('<table'), false);

const malformedHtml = renderToStaticMarkup(
  <ConfigAnalysisReportCard
    report={{
      report_id: 'report-5',
      title: '配置检查报告',
      cluster_name: 'Kubernetes - 1',
      summary: {
        total: 14,
        problematic: 5,
        healthy: 9,
        top_recommendation: '先检查结构化结果的完整性',
      },
      severity_sections: [
        {
          severity: 'mystery' as any,
          title: '未知严重级别',
          items: [
            {
              issue: '未配置存活探针',
              count: 3,
              workloads: undefined as any,
              risk: '容器异常时无法自动重启',
            },
          ],
        } as any,
        {
          severity: 'high',
          title: '缺少明细',
        } as any,
      ],
      recommendations: [],
      markdown: '# fallback',
      fallback_markdown: '# fallback',
      received_at: Date.now(),
    }}
  />
);

assert.match(malformedHtml, /结构化明细存在不完整字段，已自动跳过异常分组并降级展示/);
assert.match(malformedHtml, /未识别/);
assert.match(malformedHtml, /信息不完整/);
assert.match(malformedHtml, /当前分组缺少完整的问题明细/);
assert.match(malformedHtml, /—/);

console.log('k8s config report card test passed');
