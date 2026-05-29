import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const RabbitmqPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default RabbitmqPie;
