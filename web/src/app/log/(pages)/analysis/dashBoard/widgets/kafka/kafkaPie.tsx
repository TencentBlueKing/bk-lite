import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const KafkaPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default KafkaPie;
