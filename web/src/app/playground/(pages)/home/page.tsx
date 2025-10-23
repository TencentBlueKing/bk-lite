'use client';
import { useSearchParams } from 'next/navigation';
import { lazy, useMemo, Suspense } from 'react';
import HomePage from './components/HomePage';

const OpenPlatform = () => {
  const searchParams = useSearchParams();
  const activeComponent = searchParams.get('page');
  const componentMap: Record<string, any> = useMemo(() => ({
    'home': HomePage,
    'anomaly-detection': lazy(() => import(`./components/AnomalyDetection`)),
    'log_clustering': lazy(() => import(`./components/LogClustering`)),
    'timeseries_predict': lazy(() => import(`./components/TimeseriesPredict`)),
    'classification': lazy(() => import(`./components/Classification`))
  }), []);

  // 动态获取组件
  const DynamicComponent = useMemo(() => {
    const componentKey = activeComponent || 'home';
    return componentMap[componentKey] || HomePage;
  }, [activeComponent]);


  return (
    <>
      <div className='flex w-full flex-col'>
        <div className='w-full'>
          <Suspense>
            <DynamicComponent />
          </Suspense>
        </div>
      </div>
    </>
  )
};

export default OpenPlatform;