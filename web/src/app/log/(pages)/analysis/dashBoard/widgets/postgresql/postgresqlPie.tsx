import React from 'react';
import DockerDonutChart from '../docker/dockerDonutChart';

const PostgresqlPie: React.FC<any> = (props) => {
  return <DockerDonutChart {...props} />;
};

export default PostgresqlPie;
