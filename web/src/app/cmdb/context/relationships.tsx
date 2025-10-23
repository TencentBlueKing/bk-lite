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
    instId: string
  ) => Promise<CrentialsAssoInstItem[]>;
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
  const instId: string = searchParams.get('inst_id') || '';

  useEffect(() => {
    fetchAssoInstances(modelId, instId);
    fetchModelData();
  }, [modelId, instId]);

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
      instId: string
    ): Promise<CrentialsAssoInstItem[]> => {
      if (!modelId || !instId) return [];
      setLoading(true);
      try {
        const data = await getAssociationInstanceList(modelId, instId);
        const result = Array.isArray(data) ? data : [];
        setAssoInstances(result);
        return result;
      } catch {
        setAssoInstances([]);
        return [];
      } finally {
        setLoading(false);
      }
    },
    [getAssociationInstanceList]
  );

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
