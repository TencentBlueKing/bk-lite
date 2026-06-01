import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const WindowsEventPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default WindowsEventPie;
