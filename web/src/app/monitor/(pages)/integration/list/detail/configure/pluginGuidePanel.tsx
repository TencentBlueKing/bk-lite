'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import useIntegrationApi from '@/app/monitor/api/integration';
import MarkdownRenderer from '@/components/markdown';
import OperateDrawer from '@/components/operate-drawer';
import { PluginGuideDoc } from '@/app/monitor/types/integration';
import { PluginGuideContext } from './pluginContext';
import styles from './pluginGuidePanel.module.scss';

interface PluginGuidePanelProps {
  pluginId: string;
  pluginName?: string;
  children?: React.ReactNode;
}

const PluginGuidePanel: React.FC<PluginGuidePanelProps> = ({
  pluginId,
  pluginName,
  children
}) => {
  const { t } = useTranslation();
  const { getPluginGuide } = useIntegrationApi();
  const [visible, setVisible] = useState(false);
  const [guide, setGuide] = useState<PluginGuideDoc | null>(null);

  useEffect(() => {
    if (!pluginId) {
      setGuide(null);
      return;
    }

    let cancelled = false;
    getPluginGuide(pluginId)
      .then((data) => {
        if (!cancelled) {
          setGuide(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGuide(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [pluginId, getPluginGuide]);

  const openGuide = useCallback(() => {
    setVisible(true);
  }, []);

  const guideName = useMemo(() => {
    const fromApi = (guide?.name || '').trim();
    const sourceParts = (guide?.source || '').split('/').filter(Boolean);
    const fromSource =
      sourceParts.length >= 2 ? sourceParts[sourceParts.length - 2] : '';
    const fromPluginName = (pluginName || '').trim();
    return (
      fromApi ||
      fromPluginName ||
      fromSource ||
      t('monitor.integrations.guideFallbackName')
    );
  }, [guide, pluginName, t]);

  const getGuideTitle = useCallback(() => {
    const fallback = t('monitor.integrations.guideFallbackName');
    const safeName =
      (guideName && String(guideName).trim()) || fallback || 'Monitor';
    return t('monitor.integrations.accessAndTroubleshootGuide', undefined, {
      name: safeName
    });
  }, [t, guideName]);

  const contextValue = useMemo(
    () => ({
      openGuide,
      hasGuide: Boolean(guide?.has_guide && guide.content)
    }),
    [openGuide, guide]
  );

  return (
    <PluginGuideContext.Provider value={contextValue}>
      {children}
      {guide?.has_guide && guide.content && (
        <OperateDrawer
          title={getGuideTitle()}
          visible={visible}
          onClose={() => setVisible(false)}
          width={680}
          destroyOnClose={false}
        >
          <div className={styles.guideContent}>
            <MarkdownRenderer
              content={guide.content}
              stripDocumentTitle
              enableCodeCopy
            />
          </div>
        </OperateDrawer>
      )}
    </PluginGuideContext.Provider>
  );
};

export default PluginGuidePanel;
