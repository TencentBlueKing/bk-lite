'use client';

import React from 'react';
import { Card, Dropdown, Menu, Tag } from 'antd';
import { useRouter } from 'next/navigation';
import Icon from '@/components/icon';
import Image from 'next/image';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import styles from '@/app/opspilot/styles/common.module.scss';
import PermissionWrapper from '@/components/permission';

const { Meta } = Card;

interface EntityCardProps {
  id: string | number;
  name: string;
  introduction: string;
  created_by: string;
  team_name: string | string[];
  team: any[];
  index: number;
  online?: boolean;
  modelName?: string;
  skillType?: string;
  onMenuClick: (action: string, entity: any) => void;
  redirectUrl: string;
  iconTypeMapping: [string, string];
}

const EntityCard: React.FC<EntityCardProps> = ({
  id,
  name,
  introduction,
  created_by,
  team_name,
  team,
  index,
  online,
  modelName,
  skillType,
  onMenuClick,
  redirectUrl,
  iconTypeMapping
}) => {
  const router = useRouter();
  const { t } = useTranslation();

  const menu = (
    <Menu className={`${styles.menuContainer}`}>
      <Menu.Item key={`edit-${id}`}>
        <PermissionWrapper requiredPermissions={['Edit']}>
          <span className="block" onClick={() => onMenuClick('edit', { id, name, introduction, created_by, team_name, team, online })}>{t('common.edit')}</span>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key={`delete-${id}`}>
        <PermissionWrapper requiredPermissions={['Delete']}>
          <span className="block" onClick={() => onMenuClick('delete', { id, name, introduction, created_by, team_name, team, online })}>{t('common.delete')}</span>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  const iconType = index % 2 === 0 ? iconTypeMapping[0] : iconTypeMapping[1];
  const avatar = index % 2 === 0 ? '/app/banner_bg_1.jpg' : '/app/banner_bg_2.jpg';

  return (
    <Card
      className={`shadow-md cursor-pointer rounded-xl relative overflow-hidden ${styles.CommonCard}`}
      onClick={() => router.push(`${redirectUrl}?id=${id}&name=${name}&desc=${introduction}`)}
    >
      <div className="absolute top-2 right-2 z-10" onClick={(e) => e.stopPropagation()}>
        <Dropdown overlay={menu} trigger={['click']} key={`dropdown-${id}`} placement="bottomRight">
          <div className="cursor-pointer">
            <Icon type="sangedian-copy" className="text-xl" />
          </div>
        </Dropdown>
      </div>
      <div className="w-full h-[50px] relative">
        <Image alt="avatar" src={avatar} layout="fill" objectFit="cover" className="rounded-t-xl" />
      </div>
      <div className={`w-14 h-14 rounded-full flex justify-center items-center ${styles.iconContainer}`}>
        <Icon type={iconType} className="text-4xl" />
      </div>
      <div className="p-4 relative">
        <Meta
          title={name}
          description={
            <>
              <p className={`mt-3 mb-2 text-xs line-clamp-3 h-[50px] ${styles.desc}`}>{introduction}</p>
              <div className="flex items-end justify-between">
                <div className="font-normal flex items-center">
                  {online !== undefined && (
                    <Tag
                      color={online ? 'green' : ''}
                      className={`${styles.statusTag} ${online ? styles.online : styles.offline} px-1 mr-2`}>
                      {online ? t('studio.on') : t('studio.off')}
                    </Tag>
                  )}
                  {modelName !== undefined && modelName && (
                    <Tag className="font-mini px-[2px] leading-inherit mr-2" color="blue">{modelName}</Tag>
                  )}
                  {skillType !== undefined && skillType && (
                    <Tag className="font-mini px-[2px] leading-inherit mr-2" color="purple">{skillType}</Tag>
                  )}
                </div>
                <div className="flex items-end justify-end text-[var(--color-text-4)] font-mini w-full text-right overflow-hidden">
                  <EllipsisWithTooltip
                    text={`${t('skill.form.group')}: ${Array.isArray(team_name) ? team_name.join(',') : '--'} | ${t('skill.form.owner')}: ${created_by}`}
                    className="overflow-hidden whitespace-nowrap text-ellipsis"
                  />
                </div>
              </div>
            </>
          }
        />
      </div>
    </Card>
  );
};

export default EntityCard;

