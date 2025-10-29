import useApiClient from "@/utils/request";
import { useEffect, useState, useCallback } from "react";

// 🎯 添加类型定义
interface Category {
  id: number;
  name: string;
  description?: string;
}

interface Capability {
  id: number;
  name: string;
  description: string;
  url: string;
  category: {
    id: number;
    name?: string;
  } | number;
  is_active?: boolean;
  config?: any
}

interface ProcessedCapability {
  id: number;
  name: string;
  description: string;
  url: string;
}

interface CategoryWithCapabilities {
  category: Category;
  capabilities: ProcessedCapability[];
}

const useModelExperience = (shouldLoad: boolean = true) => {
  const [categoryList, setCategoryList] = useState<Category[]>([]);
  const [capabilityList, setCapabilityList] = useState<Capability[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadTrigger, setReloadTrigger] = useState(0);
  const { get } = useApiClient();

  const loadData = useCallback(async (isCancelled: () => boolean) => {
    try {
      setError(null);

      const [capabilityResponse, categoryResponse] = await Promise.all([
        get(`/playground/capability/`),
        get(`/playground/category/`)
      ]);

      if (isCancelled()) return;

      if (!capabilityResponse || !categoryResponse) {
        throw new Error('Failed to fetch menu data: empty response');
      }

      if (!Array.isArray(capabilityResponse) || !Array.isArray(categoryResponse)) {
        throw new Error('Invalid data format: expected arrays');
      }

      setCategoryList(categoryResponse);
      setCapabilityList(capabilityResponse);

    } catch (e) {
      if (!isCancelled()) {
        const errorMessage = e instanceof Error ? e.message : 'Unknown error occurred';
        console.error('Failed to load model experience data:', e);
        setError(errorMessage);
      }
    }
  }, [get]);

  useEffect(() => {
    if (!shouldLoad) {
      setLoading(false);
      return;
    }

    let isCancelled = false;
    const getCancelledStatus = () => isCancelled;

    setLoading(true);

    const executeLoad = async () => {
      await loadData(getCancelledStatus);

      if (!isCancelled) {
        setLoading(false);
      }
    };

    executeLoad();

    return () => {
      isCancelled = true;
    };
  }, [shouldLoad, loadData, reloadTrigger]);

  const reload = useCallback(() => {
    if (!shouldLoad) return;

    setLoading(true);
    setError(null);
    setCategoryList([]);
    setCapabilityList([]);

    // 触发重新加载
    setReloadTrigger(prev => prev + 1);
  }, [shouldLoad]);

  const renderMenu = useCallback((): CategoryWithCapabilities[] => {
    if (!categoryList.length || !capabilityList.length) {
      return [];
    }
    return categoryList.map((category: Category) => ({
      category,
      capabilities: capabilityList
        .filter((item: Capability) => {
          const categoryId = typeof item.category === 'object'
            ? item.category.id
            : item.category;

          return categoryId === category.id && item.is_active !== false;
        })
        .map((item: Capability) => ({
          id: item.id,
          name: item?.name || 'Unnamed',
          description: item?.description || '',
          url: `${item?.url}?page=${item.config?.categoryType}&id=${item?.id}&name=${encodeURIComponent(item?.name || '')}&description=${encodeURIComponent(item?.description || '')}`,
        }))
    })).filter(({ capabilities }) => capabilities.length > 0);
  }, [categoryList, capabilityList]);

  const getAllCategories = useCallback((): Category[] => {
    return categoryList;
  }, [categoryList]);

  const getCapabilitiesByCategory = useCallback((categoryId: number): ProcessedCapability[] => {
    return capabilityList
      .filter((item: Capability) => {
        const itemCategoryId = typeof item.category === 'object'
          ? item.category.id
          : item.category;
        return itemCategoryId === categoryId && item.is_active !== false;
      })
      .map((item: Capability) => ({
        id: item.id,
        name: item?.name || 'Unnamed',
        description: item?.description || '',
        url: `${item?.url}?page=anomaly-detection&id=${item?.id}&name=${encodeURIComponent(item?.name || '')}&description=${encodeURIComponent(item?.description || '')}`,
      }));
  }, [capabilityList]);

  const isDataReady = categoryList.length > 0 && capabilityList.length > 0 && !loading;

  return {
    categoryList,
    capabilityList,
    loading,
    error,
    reload,
    renderMenu,
    getAllCategories,
    getCapabilitiesByCategory,
    isDataReady,
  };
};

export default useModelExperience;