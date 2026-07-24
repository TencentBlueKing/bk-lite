import React from 'react';
import { ObjectDashboardPage } from '../common/object-dashboard-page';
import { ORACLE_DASHBOARD_CONFIG } from './config';
import styles from './index.module.scss';
export default function OracleDashboard() { return React.createElement(ObjectDashboardPage, { config: ORACLE_DASHBOARD_CONFIG, styles }); }
