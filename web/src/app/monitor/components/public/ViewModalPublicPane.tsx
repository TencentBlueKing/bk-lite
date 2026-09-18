'use client';

import React, { useEffect, useState } from 'react';
import { Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useLazyAppWidget } from '@/context/appCapabilities';
import type { AppWidgetLoader } from '@/context/appCapabilities';

type IdentifierProp = 'instUuid' | 'nodeId';

type InstUuidWidget = React.ComponentType<{
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
  onEmbedToolbar?: (toolbar: React.ReactNode) => void;
}>;

type IdentifierWidget = React.ComponentType<Record<string, string>>;

export function ViewModalPublicPane({
  active,
  loadWidget,
  identifier,
  identifierProp,
}: {
  active: boolean;
  loadWidget: AppWidgetLoader | null;
  identifier: string;
  identifierProp: IdentifierProp;
}) {
  const { t } = useTranslation();
  const [headerAction, setHeaderAction] = useState<React.ReactNode>(null);
  const [embedToolbar, setEmbedToolbar] = useState<React.ReactNode>(null);
  const { Widget, loadFailed } = useLazyAppWidget({
    loadWidget,
    active: active && Boolean(identifier),
  });

  useEffect(() => {
    setHeaderAction(null);
    setEmbedToolbar(null);
  }, [identifier]);

  const missingIdentifier = !identifier;
  const hasContent = Boolean(Widget) && !loadFailed && !missingIdentifier;
  const showHostToolbar = !embedToolbar && Boolean(headerAction);

  let body: React.ReactNode;
  if (missingIdentifier) {
    body = (
      <CompactEmptyState description={t('monitor.views.missingStableId')} />
    );
  } else if (loadFailed) {
    body = <CompactEmptyState description={t('common.loadFailed')} />;
  } else if (!Widget) {
    body = <Spin />;
  } else if (identifierProp === 'instUuid') {
    body = (
      <InstUuidMount
        key={identifier}
        Widget={Widget as InstUuidWidget}
        instUuid={identifier}
        onHeaderAction={setHeaderAction}
        onEmbedToolbar={setEmbedToolbar}
      />
    );
  } else {
    body = (
      <IdentifierMount
        key={identifier}
        Widget={Widget as IdentifierWidget}
        identifierProp={identifierProp}
        identifier={identifier}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col gap-4">
      {embedToolbar ? (
        <div className="w-full shrink-0">{embedToolbar}</div>
      ) : showHostToolbar ? (
        <div className="flex shrink-0 items-center justify-end gap-3">
          {headerAction}
        </div>
      ) : null}
      <div
        className={
          hasContent
            ? 'flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden'
            : 'flex min-h-0 min-w-0 flex-1 items-center justify-center'
        }
      >
        {body}
      </div>
    </div>
  );
}

function InstUuidMount({
  Widget,
  instUuid,
  onHeaderAction,
  onEmbedToolbar,
}: {
  Widget: InstUuidWidget;
  instUuid: string;
  onHeaderAction?: (action: React.ReactNode) => void;
  onEmbedToolbar?: (toolbar: React.ReactNode) => void;
}) {
  return (
    <Widget
      instUuid={instUuid}
      onHeaderAction={onHeaderAction}
      onEmbedToolbar={onEmbedToolbar}
    />
  );
}

function IdentifierMount({
  Widget,
  identifierProp,
  identifier,
}: {
  Widget: IdentifierWidget;
  identifierProp: Exclude<IdentifierProp, 'instUuid'>;
  identifier: string;
}) {
  return <Widget {...{ [identifierProp]: identifier }} />;
}
