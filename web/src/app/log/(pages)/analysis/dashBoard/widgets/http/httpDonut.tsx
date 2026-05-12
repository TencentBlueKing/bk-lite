import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const HttpDonut: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default HttpDonut;
