'use client';

import React, {
  useState,
  useEffect,
  forwardRef,
  useImperativeHandle,
  useCallback,
  useRef,
} from 'react';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';
import { iconList } from '@/app/cmdb/utils/common';
import { message, Spin } from 'antd';
import { useArchitectureApi } from '@/app/ops-analysis/api/architecture';
import { flattenCollections } from '@isoflow/isopacks/dist/utils';
import {
  DiagramData,
  ArchitectureProps,
} from '@/app/ops-analysis/types/architecture';
import dynamic from 'next/dynamic';
import awsIsopack from '@isoflow/isopacks/dist/aws';
import gcpIsopack from '@isoflow/isopacks/dist/gcp';
import azureIsopack from '@isoflow/isopacks/dist/azure';
import isoflowIsopack from '@isoflow/isopacks/dist/isoflow';
import kubernetesIsopack from '@isoflow/isopacks/dist/kubernetes';
import ArchitectureToolbar from './components/toolbar';
import { DEFAULT_COLORS } from '@/app/ops-analysis/constants/common';
import { svgToBase64 } from '@/app/ops-analysis/utils/common';

const Isoflow = dynamic(
  () => import('fossflow').then((mod) => ({ default: mod.Isoflow })),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" tip="Loading..." />
      </div>
    ),
  }
);

const createCmdbIsopack = async () => {
  const icons = await Promise.all(
    iconList.map(async (icon) => ({
      id: `cmdb-${icon.key}`,
      name: icon.describe || icon.key,
      url: await svgToBase64(icon.url),
      isIsometric: true,
    }))
  );
  return {
    id: 'cmdb',
    name: 'CMDB',
    icons,
  };
};

export interface ArchitectureRef {
  hasUnsavedChanges: () => boolean;
}

const Architecture = forwardRef<ArchitectureRef, ArchitectureProps>(
  ({ selectedArchitecture }, ref) => {
    const { t } = useTranslation();
    const { getArchitectureDetail, saveArchitecture } = useArchitectureApi();
    const [diagramName, setDiagramName] = useState('');
    const [fossflowKey, setFossflowKey] = useState(0);
    const [currentModel, setCurrentModel] = useState<DiagramData | null>(null);
    const [hasUnsaved, setHasUnsaved] = useState(false);
    const [loading, setLoading] = useState(false);
    const [uniqueIcons, setUniqueIcons] = useState<any[]>([]);
    const [isEditMode, setIsEditMode] = useState(false);
    const [loadedArchitectureId, setLoadedArchitectureId] = useState<
      string | null
    >(null);

    const debounceTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const lastModelUpdateRef = useRef<string>('');
    const isUpdatingRef = useRef<boolean>(false);
    const [diagramData, setDiagramData] = useState<DiagramData>(() => {
      return {
        title: 'Untitled Diagram',
        icons: [],
        colors: DEFAULT_COLORS,
        items: [],
        views: [],
        fitToScreen: true,
      };
    });

    useEffect(() => {
      let isMounted = true;
      createCmdbIsopack().then((cmdbIsopack) => {
        const allIcons = flattenCollections([
          cmdbIsopack,
          isoflowIsopack,
          awsIsopack,
          azureIsopack,
          gcpIsopack,
          kubernetesIsopack,
        ]);
        const unique = allIcons.filter(
          (icon, index, self) =>
            index === self.findIndex((i) => i.id === icon.id)
        );
        if (isMounted) {
          setUniqueIcons(unique);
        }
      });
      return () => {
        isMounted = false;
      };
    }, []);

    useEffect(() => {
      if (uniqueIcons.length === 0) return;

      const currentArchitectureId = selectedArchitecture?.data_id;

      if (
        currentArchitectureId &&
        currentArchitectureId !== loadedArchitectureId
      ) {
        (async () => {
          try {
            setLoading(true);
            isUpdatingRef.current = true;

            setCurrentModel(null);
            setDiagramData({
              title: 'Loading...',
              icons: uniqueIcons,
              colors: DEFAULT_COLORS,
              items: [],
              views: [],
              fitToScreen: true,
            });
            const data = await getArchitectureDetail(currentArchitectureId);
            const viewSets = Array.isArray(data.view_sets)
              ? { items: [], views: [] }
              : data.view_sets || { items: [], views: [] };
            if (data) {
              const mergedData: DiagramData = {
                items: viewSets.items || [],
                views: viewSets.views || [],
                title: data.name || diagramName,
                icons: uniqueIcons,
                colors: DEFAULT_COLORS,
                fitToScreen: true,
              };

              setDiagramName(data.name || '');
              setDiagramData({ ...mergedData });
              setCurrentModel({ ...mergedData });
              setFossflowKey((prev) => prev + 1);
              setHasUnsaved(false);
              setLoadedArchitectureId(currentArchitectureId);
              setIsEditMode(false);

              lastModelUpdateRef.current = JSON.stringify({
                items: viewSets.items || [],
                views: viewSets.views || [],
              });
            }
          } catch (error) {
            console.error('Load failed:', error);
            message.error(t('opsAnalysis.architecture.loadFailed'));
          } finally {
            setLoading(false);
            setTimeout(() => {
              isUpdatingRef.current = false;
            }, 1000);
          }
        })();
      } else if (!currentArchitectureId && loadedArchitectureId) {
        setCurrentModel(null);
        setDiagramData({
          title: 'Untitled Diagram',
          icons: uniqueIcons,
          colors: DEFAULT_COLORS,
          items: [],
          views: [],
          fitToScreen: true,
        });
        setFossflowKey((prev) => prev + 1);
        setHasUnsaved(false);
        setIsEditMode(false);
        setLoadedArchitectureId(null);
        lastModelUpdateRef.current = '';
      }
    }, [uniqueIcons, selectedArchitecture?.data_id, loadedArchitectureId]);

    const toggleEditMode = () => {
      const newEditMode = !isEditMode;
      setIsEditMode(newEditMode);
      if (newEditMode) {
        setHasUnsaved(false);
      }
    };

    const saveDiagram = async () => {
      if (!selectedArchitecture?.data_id || !currentModel) {
        return;
      }
      try {
        setLoading(true);

        const saveData = {
          name: diagramName,
          view_sets: {
            views: currentModel.views || [],
            items: currentModel.items || [],
          },
        };

        await saveArchitecture(selectedArchitecture.data_id, saveData);

        lastModelUpdateRef.current = JSON.stringify({
          items: currentModel.items || [],
          views: currentModel.views || [],
        });

        setHasUnsaved(false);
        setIsEditMode(false);
        message.success(t('topology.architecture.diagramSaved'));
      } catch {
        message.error(t('topology.architecture.saveFailed'));
      } finally {
        setLoading(false);
      }
    };

    const handleModelUpdated = useCallback(
      (model: DiagramData) => {
        if (isUpdatingRef.current) {
          return;
        }

        if (!selectedArchitecture?.data_id) {
          return;
        }

        try {
          const modelSnapshot = JSON.stringify({
            items: model.items || [],
            views: model.views || [],
          });

          if (modelSnapshot === lastModelUpdateRef.current) {
            return;
          }

          if (debounceTimeoutRef.current) {
            clearTimeout(debounceTimeoutRef.current);
          }

          debounceTimeoutRef.current = setTimeout(() => {
            try {
              const newModelData = {
                items: JSON.parse(JSON.stringify(model.items)) || [],
                views: JSON.parse(JSON.stringify(model.views)) || [],
              };

              setCurrentModel((prevModel) => {
                if (!prevModel) return null;
                return {
                  ...prevModel,
                  items: newModelData.items,
                  views: newModelData.views,
                };
              });
              if (isEditMode) {
                setHasUnsaved(true);
              }
              lastModelUpdateRef.current = modelSnapshot;
            } catch (error) {
              console.error('Error updating model state:', error);
            }
          }, 300);
        } catch (error) {
          console.error('Error in handleModelUpdated:', error);
        }
      },
      [selectedArchitecture?.data_id, isEditMode]
    );

    const hasUnsavedChanges = () => {
      return isEditMode && hasUnsaved;
    };

    useImperativeHandle(ref, () => ({
      hasUnsavedChanges,
    }));

    useEffect(() => {
      return () => {
        if (debounceTimeoutRef.current) {
          clearTimeout(debounceTimeoutRef.current);
        }
      };
    }, []);

    return (
      <div className="h-full flex-1 p-4 pb-0 overflow-auto flex flex-col">
        <ArchitectureToolbar
          selectedArchitecture={selectedArchitecture}
          isEditMode={isEditMode}
          loading={loading}
          onEdit={toggleEditMode}
          onSave={saveDiagram}
        />

        <div
          className={`flex-1 relative architecture-canvas ${styles.architectureCanvas}`}
          style={{ minHeight: '500px' }}
        >
          {loading && (
            <div className="absolute inset-0 bg-white bg-opacity-80 flex items-center justify-center z-50">
              <Spin size="large" />
            </div>
          )}
          <Isoflow
            key={`${fossflowKey}-edit`}
            initialData={diagramData}
            onModelUpdated={handleModelUpdated}
            editorMode={isEditMode ? 'EDITABLE' : 'EXPLORABLE_READONLY'}
          />
        </div>
      </div>
    );
  }
);

Architecture.displayName = 'Architecture';

export default Architecture;
