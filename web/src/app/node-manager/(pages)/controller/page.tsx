'use client';
import React, { useEffect, useState, useRef } from 'react';
import { Input, Tag } from 'antd';
import useApiClient from '@/utils/request';
import useNodeManagerApi from '@/app/node-manager/api';
import EntityList from '@/components/entity-list/index';
import GridEntityCard from '@/components/grid-entity-card';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import Icon from '@/components/icon';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import type { CardItem } from '@/app/node-manager/types';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import CollectorModal from '@/app/node-manager/components/sidecar/collectorModal';
import { ModalRef } from '@/app/node-manager/types';
import { useControllerMenuItem } from '@/app/node-manager/hooks/controller';
import { cloneDeep } from 'lodash';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
const { Search } = Input;

const Controller = () => {
  const router = useScreenAwareRouter();
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getControllerList } = useNodeManagerApi();
  const menuItem = useControllerMenuItem();
  const modalRef = useRef<ModalRef>(null);
  const [allControllerData, setAllControllerData] = useState<CardItem[]>([]);
  const [controllerCards, setControllerCards] = useState<CardItem[]>([]);
  const [search, setSearch] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  useEffect(() => {
    if (!isLoading) {
      fetchCollectorlist('');
    }
  }, [isLoading]);

  const navigateToCollectorDetail = (item: CardItem) => {
    router.push(`
      /node-manager/controller/detail?id=${item.id}&name=${item.original_name}&displayName=${item.name}&introduction=${item.description}&system=${item.os}&architecture=${item.cpu_architecture || ''}`);
  };

  const filterBySelected = (data: any[], selectedTags: string[]) => {
    if (!selectedTags?.length) return data;
    return data.filter((item) =>
      selectedTags.every((tag: string) => item.tagList.includes(tag))
    );
  };

  const filterBySearch = (data: any[], searchTerm: string) => {
    if (!searchTerm) return data;
    return data.filter(
      (item) =>
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.description.toLowerCase().includes(searchTerm.toLowerCase())
    );
  };

  const getOSDisplayName = (osId: string) => {
    const os = OPERATE_SYSTEMS.find(
      (item) => item.value === osId.toLowerCase()
    );
    return os ? os.label : osId;
  };

  const handleResult = (res: any, currentSearch?: string) => {
    const tagSet = new Set<string>();
    const tempdata = (res || []).map((item: any) => {
      const system = item.node_operating_system || item.os || 'linux';
      const systemDisplayName = getOSDisplayName(system);
      const architectureDisplay = item.architecture_display ||
        (item.cpu_architecture === 'arm64' ? 'ARM64' : item.cpu_architecture || '');
      const tagList = [systemDisplayName, architectureDisplay].filter(Boolean);
      tagList.forEach((tag) => {
        if (tag) {
          tagSet.add(tag);
        }
      });
      return {
        id: item.id,
        name: item.display_name,
        original_name: item.name,
        original_introduction: item.description,
        service_type: item.service_type,
        executable_path: item.executable_path,
        execute_parameters: item.execute_parameters,
        description: item.display_description || item.description || '--',
        is_pre: item.is_pre,
        icon: 'caijiqizongshu',
        tagList,
        os: system,
        cpu_architecture: item.cpu_architecture,
        originalTags: [system],
      };
    });
    setAllTags(Array.from(tagSet));
    setAllControllerData(tempdata);
    let filteredData = tempdata;
    const searchTerm = currentSearch !== undefined ? currentSearch : search;
    filteredData = filterBySearch(filteredData, searchTerm);
    filteredData = filterBySelected(filteredData, selectedTags);
    setControllerCards(filteredData);
  };

  const fetchCollectorlist = async (searchValue?: string) => {
    const params = { name: searchValue };
    try {
      setLoading(true);
      const res = await getControllerList(params);
      handleResult(res, searchValue);
    } catch (error) {
      console.error('Failed to fetch controller list:', error);
    } finally {
      setLoading(false);
    }
  };

  const openModal = (config: any) => {
    const form = cloneDeep(config?.form || {});
    if (config?.type === 'edit') {
      form.name = form.original_name;
      form.description = form.original_introduction;
    }
    modalRef.current?.showModal({
      title: config?.title,
      type: config?.type,
      form,
      key: config?.key,
    });
  };

  const handleSubmit = (type?: string) => {
    if (type === 'upload') return;
    fetchCollectorlist(search);
  };

  const buildControllerMenuItems = (data: any): MoreActionsDropdownItem[] =>
    menuItem
      .filter((item) => !['delete', 'edit'].includes(item.key))
      .map((item) => ({
        key: item.key,
        label: item.title,
        permission: item.role,
        onClick: () =>
          openModal({ ...item.config, form: data, key: 'controller' }),
      }));

  const handleTagClick = (tag: string) => {
    const newSelectedTags = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];
    setSelectedTags(newSelectedTags);
    let filteredData = allControllerData;
    filteredData = filterBySearch(filteredData, search);
    filteredData = filterBySelected(filteredData, newSelectedTags);
    setControllerCards(filteredData);
  };

  const onSearch = (searchValue: string) => {
    setSearch(searchValue);
    fetchCollectorlist(searchValue);
  };

  return (
    <div className="h-[calc(100vh-88px)] w-full">
      <EntityList
        data={controllerCards}
        loading={loading}
        filter={false}
        search={false}
        loadingContent={<CardGridSkeleton count={8} />}
        renderCard={(item: CardItem & { is_pre?: boolean }) => (
          <GridEntityCard
            name={item.name}
            description={item.description}
            icon={<Icon type={item.icon} className="text-2xl" />}
            origin={
              typeof item.is_pre === 'boolean'
                ? item.is_pre
                  ? 'builtin'
                  : 'external'
                : undefined
            }
            metaLabels={(item.tagList || []).map((tag) => String(tag))}
            menuItems={buildControllerMenuItems(item)}
            onClick={() => navigateToCollectorDetail(item)}
          />
        )}
        toolbarPrefix={
          <div className="flex items-center overflow-x-auto">
            {(allTags || []).map((tag) => (
              <Tag
                key={tag}
                color={selectedTags.includes(tag) ? 'blue' : 'default'}
                className="cursor-pointer transition-all duration-200 hover:scale-105 select-none"
                onClick={() => handleTagClick(tag)}
              >
                {tag}
              </Tag>
            ))}
          </div>
        }
        operateSection={
          <Search
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            className="w-60"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onSearch={onSearch}
          />
        }
      ></EntityList>
      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default Controller;
