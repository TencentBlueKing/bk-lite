#!/bin/bash
# mssql 采集脚本 — 用 sqlcmd 跑一组 catalog 查询,输出 JSON dict
# 设计:参考 mongodb/nginx 的 _default_discover.sh,单行 JSON
set -e

host_innerip=$(hostname -I | awk '{print $1}')
mssql_port=1433
sa_password='Testpw123!@#'

# 找到 sqlcmd(sqlcmd 在 /opt/mssql-tools/bin/ 或 /opt/mssql-tools18/bin/)
SQLCMD=$(command -v sqlcmd || echo /opt/mssql-tools/bin/sqlcmd)
if [[ ! -x "$SQLCMD" ]]; then
    SQLCMD=/opt/mssql-tools18/bin/sqlcmd
fi

# 1) SQL Server 版本
version=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -Q "SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(50))" 2>/dev/null | tr -d '[:space:]')
# 2) 实例名
server_name=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -Q "SELECT CAST(@@SERVERNAME AS NVARCHAR(128))" 2>/dev/null | tr -d '[:space:]')
# 3) Edition
edition=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -Q "SELECT CAST(SERVERPROPERTY('Edition') AS NVARCHAR(128))" 2>/dev/null | tr -d '[:space:]')
# 4) Collation
collation=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -Q "SELECT CAST(SERVERPROPERTY('Collation') AS NVARCHAR(128))" 2>/dev/null | tr -d '[:space:]')
# 5) 最大连接数
max_conn=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -Q "SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name='user connections'" 2>/dev/null | tr -d '[:space:]')
# 6) 数据库列表
databases=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -Q "SELECT name FROM sys.databases ORDER BY database_id" 2>/dev/null | grep -v '^$' | sort | tr '\n' ',' | sed 's/,$//')
# 7) 表数量(从 cmdb_test 库 — init.sql 创建的)
table_count=$("$SQLCMD" -S localhost -U sa -P "$sa_password" -C -h -1 -W -d cmdb_test -Q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'" 2>/dev/null | tr -d '[:space:]')
if [[ -z "$table_count" ]] || ! [[ "$table_count" =~ ^[0-9]+$ ]]; then
    table_count="0"
fi

# mssql 进程(MSSQL 是 SQL Server,不是 python,直接用 ps 找)
mssql_pid=$(pgrep -f "sqlservr" | head -1)
if [[ -z "$mssql_pid" ]]; then
    mssql_pid=$(pgrep -f "sqlservr.exe" | head -1)
fi

# bin_path: SQL Server 是 /opt/mssql/bin/sqlservr
bin_path="/opt/mssql/bin"
config_path="/var/opt/mssql/mssql.conf"
mssql_user="mssql"

inst_name="${host_innerip}-mssql-${mssql_port}"

cat <<EOF
{"inst_name":"${inst_name}","ip_addr":"${host_innerip}","obj_id":"mssql","port":"${mssql_port}","version":"${version}","server_name":"${server_name}","edition":"${edition}","collation":"${collation}","max_connections":"${max_conn}","databases":"${databases}","cmdb_test_table_count":"${table_count}","bin_path":"${bin_path}","config":"${config_path}","user":"${mssql_user}","pid":"${mssql_pid}"}
EOF