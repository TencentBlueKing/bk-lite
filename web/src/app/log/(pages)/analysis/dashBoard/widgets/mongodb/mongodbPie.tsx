import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const MongodbPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default MongodbPie;
