'use client';
import { useModelApi, useInstanceApi } from '@/app/cmdb/api';
import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
} from 'react';
import {
  ModelItem,
  AssoTypeItem,
  CrentialsAssoInstItem,
} from '../types/assetManage';
import { useSearchParams } from 'next/navigation';
import { useCommon } from './common';

interface RelationshipsContextType {
  modelList: ModelItem[];
  assoTypes: AssoTypeItem[];
  assoInstances: CrentialsAssoInstItem[];
  loading: boolean;
  selectedAssoId: string;
  setSelectedAssoId: (id: string) => void;
  fetchModelData: () => Promise<void>;
  fetchAssoInstances: (
    modelId: string,
    instUuid: string
  ) => Promise<CrentialsAssoInstItem[]>;
  loadAssociationPage: (modelAsstId: string) => Promise<void>;
  dropAssociationPage: (modelAsstId: string) => void;
}

const RelationshipsContext = createContext<
  RelationshipsContextType | undefined
>(undefined);

export const RelationshipsProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { getModelAssociationTypes } = useModelApi();
  const { getAssociationInstanceList } = useInstanceApi();
  const commonContext = useCommon();

  const modelList = commonContext?.modelList || [];
  const [assoTypes, setAssoTypes] = useState<AssoTypeItem[]>([]);
  const [assoInstances, setAssoInstances] = useState<CrentialsAssoInstItem[]>(
    []
  );
  const [loading, setLoading] = useState(false);
  const [selectedAssoId, setSelectedAssoId] = useState<string>('');
  const searchParams = useSearchParams();
  const modelId: string = searchParams.get('model_id') || '';
  const instUuid: string = searchParams.get('inst_uuid') || '';

  useEffect(() => {
    fetchAssoInstances(modelId, instUuid);
    fetchModelData();
  }, [modelId, instUuid]);

  const fetchModelData = useCallback(async () => {
    setLoading(true);
    try {
      const types = await getModelAssociationTypes();
      setAssoTypes(types || []);
    } finally {
      setLoading(false);
    }
  }, [getModelAssociationTypes]);

  const fetchAssoInstances = useCallback(
    async (
      modelId: string,
      instUuid: string
    ): Promise<CrentialsAssoInstItem[]> => {
      if (!modelId || !instUuid) return [];
      setLoading(true);
      try {
        const summary = await getAssociationInstanceList(modelId, instUuid, { summary: 1 });
        const groups = Array.isArray(summary) ? summary : [];
        const selected = searchParams?.get('model_asst_id') || '';
        const target = groups.find((item) => item.model_asst_id === selected && Number(item.inst_count) > 0)
          || groups.find((item) => Number(item.inst_count) > 0);
        if (target?.model_asst_id) {
          const page = await getAssociationInstanceList(modelId, instUuid, {
            model_asst_id: target.model_asst_id,
            page: 1,
            page_size: 20,
          });
          const pageGroup = Array.isArray(page) ? page[0] : null;
          if (pageGroup) {
            const index = groups.findIndex((item) => item.model_asst_id === target.model_asst_id);
            if (index >= 0) groups[index] = { ...groups[index], ...pageGroup };
          }
        }
        setAssoInstances(groups);
        return groups;
      } catch {
        setAssoInstances([]);
        return [];
      } finally {
        setLoading(false);
      }
    },
    [getAssociationInstanceList, searchParams]
  );

  const associationFlights = React.useRef(0);
  const associationQueue = React.useRef<Array<() => Promise<void>>>([]);
  const pumpAssociationQueue = useCallback(() => {
    while (associationFlights.current < 10 && associationQueue.current.length) {
      const task = associationQueue.current.shift();
      if (!task) return;
      associationFlights.current += 1;
      task().catch((error) => console.error(error)).finally(() => {
        associationFlights.current -= 1;
        pumpAssociationQueue();
      });
    }
  }, []);
  const loadAssociationPage = useCallback(async (modelAsstId: string) => {
    if (!modelId || !instUuid || !modelAsstId) return;
    associationQueue.current.push(async () => {
      const page = await getAssociationInstanceList(modelId, instUuid, {
        model_asst_id: modelAsstId,
        page: 1,
        page_size: 20,
      });
      const pageGroup = Array.isArray(page) ? page[0] : null;
      if (!pageGroup) return;
      setAssoInstances((current) => current.map((item) => (
        item.model_asst_id === modelAsstId ? { ...item, ...pageGroup } : item
      )));
    });
    pumpAssociationQueue();
  }, [getAssociationInstanceList, instUuid, modelId, pumpAssociationQueue]);

  const dropAssociationPage = useCallback((modelAsstId: string) => {
    setAssoInstances((current) => current.map((item) => (
      item.model_asst_id === modelAsstId ? { ...item, inst_list: [] } : item
    )));
  }, []);

  return (
    <RelationshipsContext.Provider
      value={{
        modelList,
        assoTypes,
        assoInstances,
        loading,
        selectedAssoId,
        setSelectedAssoId,
        fetchModelData,
        fetchAssoInstances,
        loadAssociationPage,
        dropAssociationPage,
      }}
    >
      {children}
    </RelationshipsContext.Provider>
  );
};

export const useRelationships = () => {
  const context = useContext(RelationshipsContext);
  if (context === undefined) {
    throw new Error('useRelationships must be used within a RelationshipsProvider');
  }
  return context;
};
