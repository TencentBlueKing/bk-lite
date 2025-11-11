import { useState } from 'react';
import { message } from 'antd';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';

export interface MenuGroup {
  id: string;
  name: string;
  icon?: string;
  children: FunctionMenuItem[];
}

export interface MixedItem {
  type: 'group' | 'page';
  id: string;
  data: MenuGroup | FunctionMenuItem;
}

export const useDragDrop = (
  mixedItems: MixedItem[],
  setMixedItems: React.Dispatch<React.SetStateAction<MixedItem[]>>,
  t: (key: string) => string
) => {
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragStart = (e: React.DragEvent, itemType: 'group' | 'page' | 'groupChild', data: any) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', JSON.stringify({ itemType, data }));
    setIsDragging(true);
  };

  const handleDragOver = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(targetIndex);
  };

  const handleDragEnd = () => {
    setIsDragging(false);
    setDragOverIndex(null);
  };

  const handleDropToMixedList = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverIndex(null);
    setIsDragging(false);
    
    try {
      const dragData = JSON.parse(e.dataTransfer.getData('text/plain'));
      const { itemType, data } = dragData;

      if (itemType === 'page') {
        const sourceIndex = mixedItems.findIndex(item => item.type === 'page' && (item.data as FunctionMenuItem).name === data.name);
        if (sourceIndex === -1 || sourceIndex === targetIndex) return;

        setMixedItems(prev => {
          const newItems = [...prev];
          const [movedItem] = newItems.splice(sourceIndex, 1);
          const insertIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
          newItems.splice(insertIndex, 0, movedItem);
          return newItems;
        });
      }
      else if (itemType === 'group') {
        const sourceIndex = mixedItems.findIndex(item => item.type === 'group' && item.id === data.id);
        if (sourceIndex === -1 || sourceIndex === targetIndex) return;

        setMixedItems(prev => {
          const newItems = [...prev];
          const [movedItem] = newItems.splice(sourceIndex, 1);
          const insertIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
          newItems.splice(insertIndex, 0, movedItem);
          return newItems;
        });
      }
      else if (itemType === 'groupChild') {
        const { groupId, pageIndex } = data;
        
        setMixedItems(prev => {
          const newItems = [...prev];
          const groupItemIndex = newItems.findIndex(item => item.type === 'group' && item.id === groupId);
          if (groupItemIndex === -1) return prev;
          
          const groupItem = newItems[groupItemIndex];
          const group = groupItem.data as MenuGroup;
          const page = group.children[pageIndex];
          if (!page) return prev;
          
          const newGroup = {
            ...group,
            children: group.children.filter((_, i) => i !== pageIndex)
          };
          newItems[groupItemIndex] = { ...groupItem, data: newGroup };
          
          const pageItem: MixedItem = {
            type: 'page',
            id: page.name,
            data: page
          };
          
          newItems.splice(targetIndex, 0, pageItem);
          return newItems;
        });
      }
    } catch (error) {
      console.error('Drop to mixed list failed:', error);
    }
  };

  const handleDropToGroup = (e: React.DragEvent, targetGroupId: string, targetIndex?: number) => {
    e.preventDefault();
    e.stopPropagation();
    
    try {
      const dragData = JSON.parse(e.dataTransfer.getData('text/plain'));
      const { itemType, data } = dragData;

      if (itemType === 'page') {
        const sourceIndex = mixedItems.findIndex(item => item.type === 'page' && (item.data as FunctionMenuItem).name === data.name);
        if (sourceIndex === -1) return;

        const pageItem = mixedItems[sourceIndex];
        const page = pageItem.data as FunctionMenuItem;

        setMixedItems(prev => {
          const newItems = [...prev];
          const targetGroupIndex = newItems.findIndex(item => item.type === 'group' && item.id === targetGroupId);
          if (targetGroupIndex === -1) return prev;

          const groupItem = newItems[targetGroupIndex];
          const group = groupItem.data as MenuGroup;

          if (group.children.some(c => c.name === page.name)) {
            message.warning(t('system.menu.alreadyExists'));
            return prev;
          }

          newItems.splice(sourceIndex, 1);

          const updatedGroupIndex = newItems.findIndex(item => item.type === 'group' && item.id === targetGroupId);
          const updatedGroupItem = newItems[updatedGroupIndex];
          const updatedGroup = updatedGroupItem.data as MenuGroup;

          const newChildren = [...updatedGroup.children];
          // 保留详情页模式相关属性
          const pageToAdd = {
            ...page,
            isDetailMode: page.isDetailMode,
            hiddenChildren: page.hiddenChildren
          };
          
          if (targetIndex !== undefined) {
            newChildren.splice(targetIndex, 0, pageToAdd);
          } else {
            newChildren.push(pageToAdd);
          }

          newItems[updatedGroupIndex] = {
            ...updatedGroupItem,
            data: { ...updatedGroup, children: newChildren }
          };

          return newItems;
        });
      }
      else if (itemType === 'groupChild') {
        const { groupId: sourceGroupId, pageIndex: sourceIndex } = data;
        
        if (sourceGroupId === targetGroupId && sourceIndex === targetIndex) {
          return;
        }

        setMixedItems(prev => {
          const newItems = [...prev];
          const sourceGroupIndex = newItems.findIndex(item => item.type === 'group' && item.id === sourceGroupId);
          const targetGroupIndex = newItems.findIndex(item => item.type === 'group' && item.id === targetGroupId);

          if (sourceGroupIndex === -1 || targetGroupIndex === -1) return prev;

          const sourceGroupItem = newItems[sourceGroupIndex];
          const targetGroupItem = newItems[targetGroupIndex];
          const sourceGroup = sourceGroupItem.data as MenuGroup;
          const targetGroup = targetGroupItem.data as MenuGroup;

          const [movedPage] = sourceGroup.children.splice(sourceIndex, 1);

          if (sourceGroupId === targetGroupId) {
            if (targetIndex === undefined) {
              // 如果没有指定目标索引，放到末尾
              sourceGroup.children.push(movedPage);
            } else {
              // 调整索引：如果目标位置在源位置之后，由于已经删除了源元素，索引需要减1
              let adjustedIndex = targetIndex;
              if (targetIndex > sourceIndex) {
                adjustedIndex = targetIndex - 1;
              }
              sourceGroup.children.splice(adjustedIndex, 0, movedPage);
            }
            newItems[sourceGroupIndex] = { ...sourceGroupItem, data: { ...sourceGroup, children: [...sourceGroup.children] } };
          } else {
            // 跨目录拖拽
            const insertIndex = targetIndex !== undefined ? targetIndex : targetGroup.children.length;
            targetGroup.children.splice(insertIndex, 0, movedPage);
            newItems[sourceGroupIndex] = { ...sourceGroupItem, data: { ...sourceGroup, children: [...sourceGroup.children] } };
            newItems[targetGroupIndex] = { ...targetGroupItem, data: { ...targetGroup, children: [...targetGroup.children] } };
          }

          return newItems;
        });
      }
    } catch (error) {
      console.error('Drop to group failed:', error);
    }
  };

  return {
    dragOverIndex,
    isDragging,
    handleDragStart,
    handleDragOver,
    handleDragEnd,
    handleDropToMixedList,
    handleDropToGroup,
  };
};
