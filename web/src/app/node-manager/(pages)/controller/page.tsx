'use client';
import React, { useEffect, useState, useRef, useCallback } from 'react';
import { Menu, Input, Button, Tag } from 'antd';
import useApiClient from '@/utils/request';
import useNodeManagerApi from '@/app/node-manager/api';
import EntityList from '@/components/entity-list/index';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import type { CardItem } from '@/app/node-manager/types';
import { COLLECTOR_LABEL } from '@/app/node-manager/constants/collector';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import CollectorModal from '@/app/node-manager/components/sidecar/collectorModal';
import { ModalRef } from '@/app/node-manager/types';
import PermissionWrapper from '@/components/permission';
import { useControllerMenuItem } from '@/app/node-manager/hooks/controller';
const { Search } = Input;

const Controller = () => {
  const router = useRouter();
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
      /node-manager/controller/detail?id=${item.id}&name=${item.name}&introduction=${item.description}&system=${item.tagList[0]}`);
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

  const getCollectorLabelKey = (value: string) => {
    for (const key in COLLECTOR_LABEL) {
      if (COLLECTOR_LABEL[key].includes(value)) {
        return key;
      }
    }
  };

  const getOSDisplayName = (osId: string) => {
    const os = OPERATE_SYSTEMS.find(
      (item) => item.value === osId.toLowerCase()
    );
    return os ? os.label : osId;
  };

  const handleResult = (res: any, currentSearch?: string) => {
    const tagSet = new Set<string>();
    const filter = res.filter((item: any) => !item.controller_default_run);
    const tempdata = filter.map((item: any) => {
      const system = item.node_operating_system || item.os;
      const systemDisplayName = getOSDisplayName(system);
      const tagList = [systemDisplayName];
      const label = getCollectorLabelKey(item.name);
      if (label) tagList.push(label);
      tagList.forEach((tag) => {
        if (tag) {
          tagSet.add(tag);
        }
      });
      return {
        id: item.id,
        name: item.name,
        service_type: item.service_type,
        executable_path: item.executable_path,
        execute_parameters: item.execute_parameters,
        description: item.description || '--',
        icon: 'caijiqizongshu',
        tagList,
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
    modalRef.current?.showModal({
      title: config?.title,
      type: config?.type,
      form: config?.form,
      key: config?.key,
    });
  };

  const handleSubmit = (type?: string) => {
    if (type === 'upload') return;
    fetchCollectorlist(search);
  };

  const menuActions = useCallback(
    (data: any) => {
      return (
        <Menu onClick={(e) => e.domEvent.preventDefault()}>
          {menuItem.map((item) => {
            if (['delete', 'edit'].includes(item.key)) return;
            return (
              <Menu.Item
                key={item.key}
                onClick={() =>
                  openModal({ ...item.config, form: data, key: 'controller' })
                }
                className="!p-0"
              >
                <PermissionWrapper
                  requiredPermissions={[item.role]}
                  className="!block"
                >
                  <Button type="text" className="w-full">
                    {item.title}
                  </Button>
                </PermissionWrapper>
              </Menu.Item>
            );
          })}
        </Menu>
      );
    },
    [menuItem]
  );

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
        menuActions={(value) => menuActions(value)}
        filter={false}
        search={false}
        operateSection={
          <div className="flex items-center w-full">
            <div className="flex items-center flex-1 mr-[10px] overflow-x-auto">
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
            <Search
              allowClear
              enterButton
              placeholder={`${t('common.search')}...`}
              className="w-60"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={onSearch}
            />
          </div>
        }
        onCardClick={(item: CardItem) => navigateToCollectorDetail(item)}
      ></EntityList>
      <CollectorModal ref={modalRef} onSuccess={handleSubmit} />
    </div>
  );
};

export default Controller;
