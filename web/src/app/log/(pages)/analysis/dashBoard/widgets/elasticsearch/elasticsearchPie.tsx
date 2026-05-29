import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const ElasticsearchPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default ElasticsearchPie;
