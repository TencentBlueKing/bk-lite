'use client';

import Spin from '@/components/spin';
import { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { UserItem } from '@/app/alarm/types/types';
import { CommonContextType, LevelItem, LevelMetaGroup } from '@/app/alarm/types/index';
import { useCommonApi } from '@/app/alarm/api/common';
import { useAliveController } from 'react-activation';
import { usePathname } from 'next/navigation';

const CommonContext = createContext<CommonContextType | null>(null);

const CommonContextProvider = ({ children }: { children: React.ReactNode }) => {
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [levelList, setLevelList] = useState<LevelItem[]>([]);
  const [levelMap, setLevelMap] = useState<Record<string, string>>({});
  const [levelListEvent, setLevelListEvent] = useState<LevelItem[]>([]);
  const [levelMapEvent, setLevelMapEvent] = useState<Record<string, string>>(
    {}
  );
  const [levelListIncident, setLevelListIncident] = useState<LevelItem[]>([]);
  const [levelMapIncident, setLevelMapIncident] = useState<
    Record<string, string>
  >({});
  const [levelMeta, setLevelMeta] = useState<Record<string, LevelMetaGroup>>({});
  const [pageLoading, setPageLoading] = useState(false);
  const { getUserList, getLevelList } = useCommonApi();
  const { drop } = useAliveController();
  const pathname = usePathname();
  const prevPathRef = useRef<string>(pathname);

  useEffect(() => {
    if (!drop) return;
    const prev = prevPathRef.current;
    const curr = pathname;
    const isMain = (p: string) =>
      ['/alarm/incidents', '/alarm/integration'].includes(p);

    const isDetail = (p: string) =>
      p.startsWith('/alarm/incidents/') || p.startsWith('/alarm/integration/');
    if (
      !(isMain(prev) && isDetail(curr)) &&
      !(isDetail(prev) && isMain(curr))
    ) {
      drop(prev);
    }
    prevPathRef.current = curr;
  }, [pathname]);

  const buildLevelGroup = useCallback((items: LevelItem[]) => {
    const list: LevelItem[] = items
      .slice()
      .sort((a, b) => a.level_id - b.level_id)
      .map((i) => ({
        ...i,
        label: i.level_display_name,
        value: i.level_id,
      }));
    const byId = list.reduce<Record<string, LevelItem>>((acc, cur) => {
      acc[String(cur.level_id)] = cur;
      return acc;
    }, {});
    const colorMap = list.reduce<Record<string, string>>((acc, cur) => {
      acc[String(cur.level_id)] = cur.color;
      return acc;
    }, {});
    return { list, byId, colorMap };
  }, []);

  const refreshLevels = useCallback(async () => {
    const levelRes = await getLevelList();
    const alertGroup = buildLevelGroup(
      levelRes.filter((item) => item.level_type === 'alert')
    );
    const eventGroup = buildLevelGroup(
      levelRes.filter((item) => item.level_type === 'event')
    );
    const incidentGroup = buildLevelGroup(
      levelRes.filter((item) => item.level_type === 'incident')
    );

    setLevelList(alertGroup.list);
    setLevelMap(alertGroup.colorMap);
    setLevelListEvent(eventGroup.list);
    setLevelMapEvent(eventGroup.colorMap);
    setLevelListIncident(incidentGroup.list);
    setLevelMapIncident(incidentGroup.colorMap);
    setLevelMeta({
      alert: alertGroup,
      event: eventGroup,
      incident: incidentGroup,
    });
  }, [buildLevelGroup, getLevelList]);

  const getLevelMeta = useCallback(
    (type: string, levelId: string | number | null | undefined) => {
      if (levelId === null || levelId === undefined) return undefined;
      return levelMeta[type]?.byId?.[String(levelId)];
    },
    [levelMeta]
  );

  useEffect(() => {
    const fetchAll = async () => {
      setPageLoading(true);
      try {
        const userRes = await getUserList({ page_size: 10000, page: 1 });
        setUserList(userRes.users);
        await refreshLevels();
      } finally {
        setPageLoading(false);
      }
    };
    fetchAll();
  }, [getUserList, refreshLevels]);

  return pageLoading ? (
    <Spin />
  ) : (
    <CommonContext.Provider
      value={{
        userList,
        levelList,
        levelMap,
        levelListEvent,
        levelMapEvent,
        levelListIncident,
        levelMapIncident,
        levelMeta,
        refreshLevels,
        getLevelMeta,
      }}
    >
      {children}
    </CommonContext.Provider>
  );
};

export const useCommon = () => {
  const ctx = useContext(CommonContext);
  if (!ctx)
    throw new Error('useCommon must be used within CommonContextProvider');
  return ctx;
};

export default CommonContextProvider;
