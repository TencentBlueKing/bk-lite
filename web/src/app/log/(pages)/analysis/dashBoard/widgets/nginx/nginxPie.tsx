import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const NginxPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default NginxPie;
