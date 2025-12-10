import React, { forwardRef, useImperativeHandle, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/app/monitor/components/operate-drawer';

interface DrawerRef {
  showDrawer: () => void;
}

interface CommonIssuesDrawerProps {
  content?: string;
}

const CommonIssuesDrawer = forwardRef<DrawerRef, CommonIssuesDrawerProps>(
  ({}, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);

    useImperativeHandle(ref, () => ({
      showDrawer: () => {
        setVisible(true);
      },
    }));

    const handleClose = () => {
      setVisible(false);
    };

    const issues = [
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
    ];

    return (
      <OperateModal
        title={t('monitor.integrations.k8s.commonIssues')}
        visible={visible}
        onClose={handleClose}
        width={600}
      >
        <div className="space-y-4">
          {issues.map((issue) => (
            <div
              key={issue.id}
              className="bg-[var(--color-fill-1)] p-4 rounded-lg"
            >
              <div className="flex items-start mb-3">
                <div className="bg-[var(--color-primary)] text-white rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold mr-3 flex-shrink-0">
                  {issue.id}
                </div>
                <div className="flex-1">
                  <h4 className="text-base font-semibold mb-2">
                    {issue.title}
                  </h4>
                  <div className="text-sm text-[var(--color-text-3)] mb-3">
                    <span className="font-medium">原因：</span>
                    {issue.reason}
                  </div>
                  <div className="text-sm">
                    <div className="font-medium text-[var(--color-text-2)] mb-2">
                      解决方案：
                    </div>
                    <ul className="space-y-1 pl-4">
                      {issue.solutions.map((solution, index) => (
                        <li
                          key={index}
                          className="text-[var(--color-text-3)] flex items-start"
                        >
                          <span className="mr-2">•</span>
                          <span>{solution}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </OperateModal>
    );
  }
);

CommonIssuesDrawer.displayName = 'CommonIssuesDrawer';

export default CommonIssuesDrawer;
