import React from 'react';
import DockerKpiCard from '../docker/dockerKpiCard';

const MysqlKpiCard: React.FC<any> = (props) => {
  return <DockerKpiCard {...props} />;
};

export default MysqlKpiCard;
