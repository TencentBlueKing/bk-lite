'use client';

import { CmdbPublicWidgetPage } from '@/app/cmdb/components/public/CmdbPublicWidgetPage';

export default function Page() {
  return (
    <CmdbPublicWidgetPage
      widgetKey="monitor.monitorView"
      identifierProp="monitorId"
    />
  );
}
