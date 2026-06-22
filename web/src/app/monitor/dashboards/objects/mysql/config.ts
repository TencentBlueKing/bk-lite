import { MysqlMetricConfig, TrendLegendItem } from './types';

export const MYSQL_COLLECTION_STATUS_QUERY = "count({instance_type='mysql', collect_type='database', __$labels__}) by (instance_id)";

export const DASHBOARD_METRICS: MysqlMetricConfig[] = [
  {
    name: 'mysql_uptime',
    display_name: 'MySQL 运行时长',
    description: '实例自上次启动以来的持续运行时间。',
    unit: 's',
    query: 'mysql_uptime{__$labels__}',
    color: '#597ef7'
  },
  {
    name: 'mysql_threads_connected',
    display_name: '当前连接数',
    description: '当前已建立连接数量，直接反映连接压力。',
    unit: 'counts',
    query: 'mysql_threads_connected{__$labels__}',
    color: '#2f6bff'
  },
  {
    name: 'mysql_threads_running',
    display_name: '活跃线程数',
    description: '当前正在执行查询的线程数量。',
    unit: 'counts',
    query: 'mysql_threads_running{__$labels__}',
    color: '#ff8a1f'
  },
  {
    name: 'mysql_variables_max_connections',
    display_name: '最大连接配置值',
    description: 'max_connections 配置值，用作真实连接容量基线。',
    unit: 'counts',
    query: 'mysql_variables_max_connections{__$labels__}',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_connection_utilization',
    display_name: '连接使用率',
    description: '当前连接数占 max_connections 配置值的比例。',
    unit: 'percent',
    query:
      'clamp_max(100 * max by (instance_id) (mysql_threads_connected{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (mysql_variables_max_connections{__$labels__}), 1), 100)',
    color: '#ff8a1f'
  },
  {
    name: 'mysql_max_used_connections',
    display_name: '历史最大连接数',
    description: '实例运行以来使用过的最大连接数。',
    unit: 'counts',
    query: 'mysql_max_used_connections{__$labels__}',
    color: '#8a5cff'
  },
  {
    name: 'mysql_threads_cached',
    display_name: '缓存线程数',
    description: '可复用线程数量，反映连接复用效率。',
    unit: 'counts',
    query: 'mysql_threads_cached{__$labels__}',
    color: '#4d9fff'
  },
  {
    name: 'mysql_process_list_threads_idle',
    display_name: '空闲线程数',
    description: '来自 process list 的 idle 线程数量。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_process_list_threads_idle{__$labels__})',
    color: '#2f6bff'
  },
  {
    name: 'mysql_process_list_threads_executing',
    display_name: '执行线程数',
    description: '来自 process list 的 executing 线程数量。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_process_list_threads_executing{__$labels__})',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_process_list_threads_sending_data',
    display_name: '发送数据线程数',
    description: '来自 process list 的 sending data 线程数量。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_process_list_threads_sending_data{__$labels__})',
    color: '#faad14'
  },
  {
    name: 'mysql_process_list_threads_waiting_for_lock',
    display_name: '锁等待线程数',
    description: '来自 process list 的 waiting for lock 线程数量。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_process_list_threads_waiting_for_lock{__$labels__})',
    color: '#5b8ff9'
  },
  {
    name: 'mysql_queries_rate',
    display_name: '查询吞吐速率',
    description: '整体查询吞吐量，用于评估总访问压力。',
    unit: 'cps',
    query: 'rate(mysql_queries{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mysql_questions_rate',
    display_name: '请求语句速率',
    description: '客户端发起语句速率，衡量入口请求压力。',
    unit: 'cps',
    query: 'rate(mysql_questions{__$labels__}[5m])',
    color: '#597ef7'
  },
  {
    name: 'mysql_slow_queries_rate',
    display_name: '慢查询速率',
    description: '慢查询触发频次，用于评估 SQL 性能风险。',
    unit: 'cps',
    query: 'rate(mysql_slow_queries{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_com_select_rate',
    display_name: '查询语句速率',
    description: '读请求速率，反映查询读负载。',
    unit: 'cps',
    query: 'rate(mysql_com_select{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mysql_com_insert_rate',
    display_name: '插入语句速率',
    description: '写入请求速率。',
    unit: 'cps',
    query: 'rate(mysql_com_insert{__$labels__}[5m])',
    color: '#ff9f43'
  },
  {
    name: 'mysql_com_update_rate',
    display_name: '更新语句速率',
    description: '更新请求速率。',
    unit: 'cps',
    query: 'rate(mysql_com_update{__$labels__}[5m])',
    color: '#faad14'
  },
  {
    name: 'mysql_com_delete_rate',
    display_name: '删除语句速率',
    description: '删除请求速率。',
    unit: 'cps',
    query: 'rate(mysql_com_delete{__$labels__}[5m])',
    color: '#ff7875'
  },
  {
    name: 'mysql_innodb_row_lock_time_avg',
    display_name: '平均行锁等待时间',
    description: '行锁等待平均耗时，过高通常意味着锁争用。',
    unit: 'ms',
    query: 'mysql_innodb_row_lock_time_avg{__$labels__}',
    color: '#ff7875'
  },
  {
    name: 'mysql_innodb_row_lock_waits_rate',
    display_name: '行锁等待速率',
    description: 'InnoDB 行锁等待发生频次。',
    unit: 'cps',
    query: 'rate(mysql_innodb_row_lock_waits{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_innodb_data_reads_rate',
    display_name: 'InnoDB 物理读速率',
    description: 'InnoDB 物理读操作速率。',
    unit: 'cps',
    query: 'rate(mysql_innodb_data_reads{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mysql_innodb_data_writes_rate',
    display_name: 'InnoDB 物理写速率',
    description: 'InnoDB 物理写操作速率。',
    unit: 'cps',
    query: 'rate(mysql_innodb_data_writes{__$labels__}[5m])',
    color: '#52c41a'
  },
  {
    name: 'mysql_innodb_os_log_fsyncs_rate',
    display_name: 'Redo 刷盘',
    description: 'Redo 日志刷盘频率，反映事务提交压力。',
    unit: 'cps',
    query: 'rate(mysql_innodb_os_log_fsyncs{__$labels__}[5m])',
    color: '#fa8c16'
  },
  {
    name: 'mysql_innodb_buffer_pool_read_requests_rate',
    display_name: '缓冲池读请求速率',
    description: '逻辑读请求速率，衡量缓存读取压力。',
    unit: 'cps',
    query: 'rate(mysql_innodb_buffer_pool_read_requests{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mysql_innodb_buffer_pool_reads_rate',
    display_name: '磁盘读取速率',
    description: '需要从磁盘读取的缓冲池未命中速率。',
    unit: 'cps',
    query: 'rate(mysql_innodb_buffer_pool_reads{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_buffer_pool_hit_ratio',
    display_name: '缓冲池命中率',
    description: '逻辑读由缓存命中的比例。',
    unit: 'percent',
    query:
      '100 * (1 - rate(mysql_innodb_buffer_pool_reads{__$labels__}[5m]) / clamp_min(rate(mysql_innodb_buffer_pool_read_requests{__$labels__}[5m]), 1e-6))',
    color: '#52c41a'
  },
  {
    name: 'mysql_buffer_pool_used_ratio',
    display_name: '缓冲池使用率',
    description: '缓冲池已使用页占比。',
    unit: 'percent',
    query:
      '100 * (mysql_innodb_buffer_pool_pages_total{__$labels__} - mysql_innodb_buffer_pool_pages_free{__$labels__}) / clamp_min(mysql_innodb_buffer_pool_pages_total{__$labels__}, 1)',
    color: '#2f6bff'
  },
  {
    name: 'mysql_buffer_pool_dirty_ratio',
    display_name: '脏页占比',
    description: '脏页页数占缓冲池总页数的比例。',
    unit: 'percent',
    query:
      '100 * mysql_innodb_buffer_pool_pages_dirty{__$labels__} / clamp_min(mysql_innodb_buffer_pool_pages_total{__$labels__}, 1)',
    color: '#faad14'
  },
  {
    name: 'mysql_innodb_buffer_pool_pages_total',
    display_name: '缓冲池总页数',
    description: '缓冲池总页数。',
    unit: 'counts',
    query: 'mysql_innodb_buffer_pool_pages_total{__$labels__}',
    color: '#597ef7'
  },
  {
    name: 'mysql_innodb_buffer_pool_pages_dirty',
    display_name: '脏页数',
    description: '尚未刷盘的脏页数量。',
    unit: 'counts',
    query: 'mysql_innodb_buffer_pool_pages_dirty{__$labels__}',
    color: '#faad14'
  },
  {
    name: 'mysql_innodb_buffer_pool_pages_free',
    display_name: '空闲页数',
    description: '缓冲池空闲页数。',
    unit: 'counts',
    query: 'mysql_innodb_buffer_pool_pages_free{__$labels__}',
    color: '#73d13d'
  },
  {
    name: 'mysql_bytes_received_rate',
    display_name: '接收流量',
    description: 'MySQL 输入流量速率。',
    unit: 'byteps',
    query: 'rate(mysql_bytes_received{__$labels__}[5m])',
    color: '#13c2c2'
  },
  {
    name: 'mysql_bytes_sent_rate',
    display_name: '发送流量',
    description: 'MySQL 输出流量速率。',
    unit: 'byteps',
    query: 'rate(mysql_bytes_sent{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mysql_table_open_cache_hits_rate',
    display_name: '表缓存命中率',
    description: '表缓存请求命中比例。',
    unit: 'percent',
    query:
      '100 * rate(mysql_table_open_cache_hits{__$labels__}[5m]) / clamp_min(rate(mysql_table_open_cache_hits{__$labels__}[5m]) + rate(mysql_table_open_cache_misses{__$labels__}[5m]), 1e-6)',
    color: '#52c41a'
  },
  {
    name: 'mysql_variables_table_open_cache',
    display_name: '表缓存配置值',
    description: 'table_open_cache 配置值，用于判断表句柄容量。',
    unit: 'counts',
    query: 'mysql_variables_table_open_cache{__$labels__}',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_variables_open_files_limit',
    display_name: '文件句柄上限配置值',
    description: 'open_files_limit 配置值，用于判断文件句柄容量。',
    unit: 'counts',
    query: 'mysql_variables_open_files_limit{__$labels__}',
    color: '#6f7f95'
  },
  {
    name: 'mysql_table_open_cache_misses_rate',
    display_name: '表缓存未命中速率',
    description: '表缓存 miss 速率。',
    unit: 'cps',
    query: 'rate(mysql_table_open_cache_misses{__$labels__}[5m])',
    color: '#ff7875'
  },
  {
    name: 'mysql_open_tables',
    display_name: '当前打开表数',
    description: '正在打开的表句柄数量。',
    unit: 'counts',
    query: 'mysql_open_tables{__$labels__}',
    color: '#597ef7'
  },
  {
    name: 'mysql_opened_tables_rate',
    display_name: '打开表速率',
    description: '表重新打开速率，高值通常说明缓存不足。',
    unit: 'cps',
    query: 'rate(mysql_opened_tables{__$labels__}[5m])',
    color: '#fa8c16'
  },
  {
    name: 'mysql_open_files',
    display_name: '打开文件数',
    description: 'MySQL 当前文件句柄占用。',
    unit: 'counts',
    query: 'mysql_open_files{__$labels__}',
    color: '#8a5cff'
  },
  {
    name: 'mysql_key_reads_rate',
    display_name: '键缓存磁盘读取速率',
    description: 'MyISAM 键缓存从磁盘读取键块的速率。',
    unit: 'cps',
    query: 'rate(mysql_key_reads{__$labels__}[5m])',
    color: '#7f56d9'
  },
  {
    name: 'mysql_key_read_requests_rate',
    display_name: '键缓存读取请求速率',
    description: 'MyISAM 键缓存逻辑读取请求速率。',
    unit: 'cps',
    query: 'rate(mysql_key_read_requests{__$labels__}[5m])',
    color: '#9254de'
  },
  {
    name: 'mysql_key_cache_hit_ratio',
    display_name: '键缓存命中率',
    description: 'MyISAM 键缓存命中率。',
    unit: 'percent',
    query:
      '100 * (1 - rate(mysql_key_reads{__$labels__}[5m]) / clamp_min(rate(mysql_key_read_requests{__$labels__}[5m]), 1e-6))',
    color: '#52c41a'
  },
  {
    name: 'mysql_variables_innodb_buffer_pool_size',
    display_name: '缓冲池配置大小',
    description: 'innodb_buffer_pool_size 配置值，用于衡量缓存容量基线。',
    unit: 'bytes',
    query: 'mysql_variables_innodb_buffer_pool_size{__$labels__}',
    color: '#6f7f95'
  },
  {
    name: 'mysql_created_tmp_tables_rate',
    display_name: '临时表总速率',
    description: '内存与磁盘临时表总创建速率。',
    unit: 'cps',
    query: 'rate(mysql_created_tmp_tables{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mysql_created_tmp_disk_tables_rate',
    display_name: '磁盘临时表速率',
    description: '落盘临时表创建速率。',
    unit: 'cps',
    query: 'rate(mysql_created_tmp_disk_tables{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_created_tmp_memory_tables_rate',
    display_name: '内存临时表速率',
    description: '仅在内存中创建的临时表速率，可用于对比落盘压力。',
    unit: 'cps',
    query:
      'clamp_min(rate(mysql_created_tmp_tables{__$labels__}[5m]) - rate(mysql_created_tmp_disk_tables{__$labels__}[5m]), 0)',
    color: '#fa8c16'
  },
  {
    name: 'mysql_variables_tmp_table_size',
    display_name: '临时表内存阈值',
    description: 'tmp_table_size 配置值，用于判断临时表内存上限。',
    unit: 'bytes',
    query: 'mysql_variables_tmp_table_size{__$labels__}',
    color: '#6f7f95'
  },
  {
    name: 'mysql_variables_max_heap_table_size',
    display_name: '堆临时表内存阈值',
    description: 'max_heap_table_size 配置值，用于判断内存临时表容量上限。',
    unit: 'bytes',
    query: 'mysql_variables_max_heap_table_size{__$labels__}',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_variables_read_only',
    display_name: '只读状态',
    description: '实例 read_only 配置值，通常 1 表示只读。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_variables_read_only{__$labels__})',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_variables_super_read_only',
    display_name: '超级只读状态',
    description: '实例 super_read_only 配置值，通常 1 表示超级只读。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_variables_super_read_only{__$labels__})',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_variables_log_bin',
    display_name: '二进制日志状态',
    description: '实例 log_bin 配置值，通常 1 表示开启 binlog。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_variables_log_bin{__$labels__})',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_variables_log_slave_updates',
    display_name: '复制回放写入日志状态',
    description: '实例 log_slave_updates 配置值，通常 1 表示记录复制回放写入。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_variables_log_slave_updates{__$labels__})',
    color: '#9aa9bf'
  },
  {
    name: 'mysql_tmp_disk_table_ratio',
    display_name: '磁盘临时表占比',
    description: '临时表落盘比例，过高通常需要优化 SQL 或内存。',
    unit: 'percent',
    query:
      '100 * rate(mysql_created_tmp_disk_tables{__$labels__}[5m]) / clamp_min(rate(mysql_created_tmp_tables{__$labels__}[5m]), 1e-6)',
    color: '#ff7875'
  },
  {
    name: 'mysql_aborted_connects',
    display_name: '中断连接数',
    description: '连接尝试失败累计值。',
    unit: 'counts',
    query: 'mysql_aborted_connects{__$labels__}',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_aborted_connects_rate',
    display_name: '中断连接速率',
    description: '连接尝试失败速率。',
    unit: 'cps',
    query: 'rate(mysql_aborted_connects{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_aborted_clients',
    display_name: '异常断开客户端数',
    description: '客户端异常断开累计值。',
    unit: 'counts',
    query: 'mysql_aborted_clients{__$labels__}',
    color: '#ff7875'
  },
  {
    name: 'mysql_aborted_clients_rate',
    display_name: '异常断开客户端速率',
    description: '客户端异常断开速率。',
    unit: 'cps',
    query: 'rate(mysql_aborted_clients{__$labels__}[5m])',
    color: '#ff7875'
  },
  {
    name: 'mysql_connection_errors_internal',
    display_name: '内部连接错误数',
    description: '服务端内部错误导致的连接失败累计值。',
    unit: 'counts',
    query: 'mysql_connection_errors_internal{__$labels__}',
    color: '#ff7875'
  },
  {
    name: 'mysql_slave_seconds_behind_master',
    display_name: '复制延迟',
    description: '从库相对主库落后的秒数。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_slave_seconds_behind_master{__$labels__})',
    color: '#2f6bff'
  },
  {
    name: 'mysql_slave_io_running',
    display_name: '复制 IO 线程状态',
    description: '从库复制 IO 线程状态，通常 1 为运行。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_slave_slave_io_running_int{__$labels__})',
    color: '#27c274'
  },
  {
    name: 'mysql_slave_sql_running',
    display_name: '复制 SQL 线程状态',
    description: '从库复制 SQL 线程状态，通常 1 为运行。',
    unit: 'counts',
    query: 'max by (instance_id) (mysql_slave_slave_sql_running_int{__$labels__})',
    color: '#27c274'
  },
  {
    name: 'mysql_connection_errors_max_connections',
    display_name: '连接上限错误数',
    description: '因达到 max_connections 导致的拒绝连接累计值。',
    unit: 'counts',
    query: 'mysql_connection_errors_max_connections{__$labels__}',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_connection_errors_max_connections_rate',
    display_name: '连接上限错误速率',
    description: '因达到 max_connections 导致的拒绝连接速率。',
    unit: 'cps',
    query: 'rate(mysql_connection_errors_max_connections{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_connection_errors_peer_address',
    display_name: '对端地址连接错误数',
    description: '因对端地址非法或被拒绝导致的连接失败累计值。',
    unit: 'counts',
    query: 'mysql_connection_errors_peer_address{__$labels__}',
    color: '#ff7875'
  },
  {
    name: 'mysql_connection_errors_select',
    display_name: '轮询连接错误数',
    description: '在 socket select 处理阶段发生的连接失败累计值。',
    unit: 'counts',
    query: 'mysql_connection_errors_select{__$labels__}',
    color: '#ffa940'
  },
  {
    name: 'mysql_connection_errors_tcpwrap',
    display_name: '访问控制连接错误数',
    description: '因 TCP Wrapper 访问控制导致的连接失败累计值。',
    unit: 'counts',
    query: 'mysql_connection_errors_tcpwrap{__$labels__}',
    color: '#ff4d4f'
  },
  {
    name: 'mysql_innodb_data_fsyncs_rate',
    display_name: 'InnoDB 数据文件刷盘速率',
    description: 'InnoDB 数据文件执行刷盘的速率。',
    unit: 'cps',
    query: 'rate(mysql_innodb_data_fsyncs{__$labels__}[5m])',
    color: '#597ef7'
  },
  {
    name: 'mysql_open_files_utilization',
    display_name: '文件句柄使用率',
    description: '当前打开文件数占 open_files_limit 配置值的比例。',
    unit: 'percent',
    query:
      'clamp_max(100 * max by (instance_id) (mysql_open_files{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (mysql_variables_open_files_limit{__$labels__}), 1), 100)',
    color: '#13c2c2'
  },
  {
    name: 'mysql_table_open_cache_utilization',
    display_name: '表缓存使用率',
    description: '当前打开表数占 table_open_cache 配置值的比例。',
    unit: 'percent',
    query:
      'clamp_max(100 * max by (instance_id) (mysql_open_tables{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (mysql_variables_table_open_cache{__$labels__}), 1), 100)',
    color: '#2f6bff'
  }
];

export const DEFAULT_METRIC_COLORS = ['#2f6bff', '#27c274', '#ff8a1f', '#ff4d4f', '#8a5cff', '#13c2c2', '#faad14', '#597ef7'];

export const DASHBOARD_METRIC_MAP = new Map(DASHBOARD_METRICS.map((metric) => [metric.name, metric]));

export const DASHBOARD_FALLBACK_GROUPS: Record<string, string> = {
  mysql_uptime: 'Base',
  mysql_threads_connected: 'ConnStatus',
  mysql_threads_running: 'ConnStatus',
  mysql_threads_cached: 'ConnStatus',
  mysql_process_list_threads_idle: 'ConnStatus',
  mysql_process_list_threads_executing: 'ConnStatus',
  mysql_process_list_threads_sending_data: 'ConnStatus',
  mysql_process_list_threads_waiting_for_lock: 'ConnStatus',
  mysql_variables_max_connections: 'ConnStatus',
  mysql_max_used_connections: 'ConnStatus',
  mysql_aborted_connects: 'ConnStatus',
  mysql_aborted_connects_rate: 'ConnStatus',
  mysql_aborted_clients: 'ConnStatus',
  mysql_aborted_clients_rate: 'ConnStatus',
  mysql_connection_errors_internal: 'ConnStatus',
  mysql_connection_errors_max_connections: 'ConnStatus',
  mysql_connection_errors_max_connections_rate: 'ConnStatus',
  mysql_connection_errors_peer_address: 'ConnStatus',
  mysql_connection_errors_select: 'ConnStatus',
  mysql_connection_errors_tcpwrap: 'ConnStatus',
  mysql_connection_utilization: 'ConnStatus',
  mysql_slave_seconds_behind_master: 'Replication',
  mysql_slave_io_running: 'Replication',
  mysql_slave_sql_running: 'Replication',
  mysql_slow_queries_rate: 'QueryPerf',
  mysql_queries_rate: 'QueryPerf',
  mysql_questions_rate: 'QueryPerf',
  mysql_com_select_rate: 'QueryPerf',
  mysql_com_insert_rate: 'QueryPerf',
  mysql_com_update_rate: 'QueryPerf',
  mysql_com_delete_rate: 'QueryPerf',
  mysql_innodb_row_lock_time_avg: 'InnoDBPerf',
  mysql_innodb_row_lock_waits_rate: 'InnoDBPerf',
  mysql_innodb_data_reads_rate: 'InnoDBPerf',
  mysql_innodb_data_writes_rate: 'InnoDBPerf',
  mysql_innodb_data_fsyncs_rate: 'InnoDBPerf',
  mysql_innodb_os_log_fsyncs_rate: 'InnoDBPerf',
  mysql_innodb_buffer_pool_read_requests_rate: 'InnoDBPerf',
  mysql_innodb_buffer_pool_reads_rate: 'InnoDBPerf',
  mysql_innodb_buffer_pool_pages_free: 'InnoDBPerf',
  mysql_innodb_buffer_pool_pages_dirty: 'InnoDBPerf',
  mysql_innodb_buffer_pool_pages_total: 'InnoDBPerf',
  mysql_buffer_pool_hit_ratio: 'InnoDBPerf',
  mysql_buffer_pool_dirty_ratio: 'InnoDBPerf',
  mysql_buffer_pool_used_ratio: 'InnoDBPerf',
  mysql_bytes_received_rate: 'NetTraffic',
  mysql_bytes_sent_rate: 'NetTraffic',
  mysql_variables_table_open_cache: 'TableCache',
  mysql_variables_open_files_limit: 'TableCache',
  mysql_open_tables: 'TableCache',
  mysql_opened_tables_rate: 'TableCache',
  mysql_open_files: 'TableCache',
  mysql_open_files_utilization: 'TableCache',
  mysql_table_open_cache_utilization: 'TableCache',
  mysql_table_open_cache_hits_rate: 'TableCache',
  mysql_table_open_cache_misses_rate: 'TableCache',
  mysql_key_reads_rate: 'KeyCache',
  mysql_key_read_requests_rate: 'KeyCache',
  mysql_key_cache_hit_ratio: 'KeyCache',
  mysql_variables_tmp_table_size: 'TempTable',
  mysql_variables_max_heap_table_size: 'TempTable',
  mysql_variables_innodb_buffer_pool_size: 'InnoDBPerf',
  mysql_created_tmp_disk_tables_rate: 'TempTable',
  mysql_created_tmp_memory_tables_rate: 'TempTable',
  mysql_created_tmp_tables_rate: 'TempTable',
  mysql_tmp_disk_table_ratio: 'TempTable'
};

export const TREND_LEGENDS: Record<string, TrendLegendItem[]> = {
  qps: [
    { label: 'QPS', color: '#2f6bff', primary: true },
    { label: '慢查询速率', color: '#ff4d4f' }
  ],
  connection: [
    { label: '当前连接数', color: '#2f6bff', primary: true },
    { label: '执行线程数', color: '#ff8a1f' }
  ],
  innodb: [
    { label: '读 IOPS', color: '#2f6bff', primary: true },
    { label: '写 IOPS', color: '#27c274' },
    { label: 'Redo', color: '#ff8a1f' }
  ],
  network: [
    { label: '接收速率', color: '#2f6bff', primary: true },
    { label: '发送速率', color: '#27c274' }
  ],
  lockWaits: [{ label: '行锁等待速率', color: '#ff4d4f', primary: true }],
  replication: [{ label: '复制延迟', color: '#2f6bff', primary: true }]
};
