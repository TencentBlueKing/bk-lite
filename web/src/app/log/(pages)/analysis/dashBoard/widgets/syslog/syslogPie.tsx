import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const SyslogPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default SyslogPie;
