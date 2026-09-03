import React from 'react';
import type { MonitorObjectSnapshot } from '@/app/alarm/types/alarms';

interface MonitorObjectListProps {
  objects: MonitorObjectSnapshot[];
}

const PLACEHOLDER = '--';

const MonitorObjectList: React.FC<MonitorObjectListProps> = ({ objects }) => (
  <div className="space-y-1">
    {objects.map((object) => (
      <div key={object.monitor_id} className="break-words">
        {object.resource_type || PLACEHOLDER}：
        {object.resource_name || PLACEHOLDER}
      </div>
    ))}
  </div>
);

export default MonitorObjectList;
