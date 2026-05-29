import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const ApachePie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default ApachePie;
