import type React from 'react';
import type { K8sCommonIssue } from './index';

type TranslateFn = (key: string) => React.ReactNode;

export interface K8sCommonIssuesPreset {
  title: React.ReactNode;
  reasonLabel: React.ReactNode;
  solutionLabel: React.ReactNode;
  issues: K8sCommonIssue[];
}

export const createMonitorK8sCommonIssuesPreset = (
  title: React.ReactNode,
): K8sCommonIssuesPreset => ({
  title,
  reasonLabel: '原因：',
  solutionLabel: '解决方案：',
  issues: [
    {
      id: 1,
      title: 'Pod 一直处于 Pending 状态',
      reason: '集群资源不足',
      solutions: [
        '检查节点资源使用情况：kubectl top nodes',
        '调整资源请求或增加集群节点',
      ],
    },
    {
      id: 2,
      title: 'Pod 无法连接 NATS 服务',
      reason: '网络不通或认证证书错误',
      solutions: ['查看 Pod 日志获取详细错误信息'],
    },
  ],
});

export const createLogK8sCommonIssuesPreset = (
  t: TranslateFn,
): K8sCommonIssuesPreset => ({
  title: t('log.integration.k8s.commonIssues'),
  reasonLabel: t('log.integration.k8s.reasonLabel'),
  solutionLabel: t('log.integration.k8s.solutionLabel'),
  issues: [
    {
      id: 1,
      title: t('log.integration.k8s.commonIssuePendingTitle'),
      reason: t('log.integration.k8s.commonIssuePendingReason'),
      solutions: [
        t('log.integration.k8s.commonIssuePendingSolution1'),
        t('log.integration.k8s.commonIssuePendingSolution2'),
      ],
    },
    {
      id: 2,
      title: t('log.integration.k8s.commonIssueNatsTitle'),
      reason: t('log.integration.k8s.commonIssueNatsReason'),
      solutions: [
        t('log.integration.k8s.commonIssueNatsSolution1'),
        t('log.integration.k8s.commonIssueNatsSolution2'),
      ],
    },
    {
      id: 3,
      title: t('log.integration.k8s.commonIssueMountTitle'),
      reason: t('log.integration.k8s.commonIssueMountReason'),
      solutions: [
        t('log.integration.k8s.commonIssueMountSolution1'),
        t('log.integration.k8s.commonIssueMountSolution2'),
      ],
    },
  ],
});
