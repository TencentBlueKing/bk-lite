'use client'
import React, { useCallback, useMemo } from 'react';
import {
  useSearchParams,
} from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useRouter } from 'next/navigation';
import AnomalyDetail from './components/anomaly/AnomalyDetail';
import RasaDetail from './components/rasa/RasaDetail';
import LogDetail from './components/log/LogDetail';
import TimeSeriesPredict from './components/timeseries/TimeSeriesPredict';
import ClassificationDetail from './components/classification/classificationDetail';
import ImageClassificationDetail from './components/image-classification/imageClassificationDetail';
import ObjectDetectionDetail from './components/object-detection/objectDetection';
import Sublayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';
import { MenuItem } from '@/types';
import { RasaMenus } from '@/app/mlops/types/manage';
import { RASA_MENUS } from '@/app/mlops/constants'


const Detail = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    folder_id,
    folder_name,
    description,
    activeTap,
    menu,
  } = useMemo(() => ({
    folder_id: searchParams.get('folder_id') || '',
    folder_name: searchParams.get('folder_name') || '',
    description: searchParams.get('description') || '',
    activeTap: searchParams.get('activeTap') || '',
    menu: searchParams.get('menu') || '',
  }), [searchParams]);

  const datasetInfo = `folder_id=${folder_id}&folder_name=${folder_name}&description=${description}&activeTap=${activeTap}`;

  const RasaContent = (menu: string) => {
    const result =  RASA_MENUS.find((item: RasaMenus) => item.menu === menu);
    if(result) return result.content;
    return '';
  };

  const renderMenus = useCallback((menus: RasaMenus[]): MenuItem[] => {
    return menus.map(({ menu, icon }) => ({
      name: menu,
      title: t(`datasets.${menu}Title`),
      icon: icon,
      url: `/mlops/manage/detail?${datasetInfo}&menu=${menu}`,
      operation: []
    }));
  }, [datasetInfo]);

  const showSideMenu = useMemo(() => {
    return activeTap !== 'rasa' ? false : true;
  }, [activeTap]);

  const renderPage: Record<string, React.ReactNode> = useMemo(() => ({
    anomaly_detection: <AnomalyDetail />,
    rasa: <RasaDetail />,
    log_clustering: <LogDetail />,
    timeseries_predict: <TimeSeriesPredict />,
    classification: <ClassificationDetail />,
    image_classification: <ImageClassificationDetail />,
    object_detection: <ObjectDetectionDetail />
  }), [activeTap]);

  const Intro = useMemo(() => (
    <div className="flex h-[58px] flex-col items-center justify-center">
      <h2 className="text-base font-semibold mb-2">{folder_name}</h2>
      <h1 className="text-center">{description}</h1>
    </div>
  ), [folder_name]);

  const topSection = useMemo(() => {
    if (menu)
      return <TopSection title={t(`datasets.${menu}`)} content={RasaContent(menu)} />;
    return <TopSection title={folder_name} content={description} />;
  }, [menu]);

  const backToList = () => router.push(`/mlops/manage/list`);

  return (
    <>
      <div className='w-full'>
        <Sublayout
          intro={Intro}
          topSection={topSection}
          showSideMenu={showSideMenu}
          activeKeyword
          keywordName='menu'
          customMenuItems={activeTap === 'rasa' ? renderMenus(RASA_MENUS) : []}
          onBackButtonClick={backToList}
        >
          <div className='w-full h-full relative'>
            {renderPage[activeTap]}
          </div>
        </Sublayout>
      </div>
    </>
  )
};

export default Detail;