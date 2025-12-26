#!/bin/bash

bk_host_innerip={{bk_host_innerip}}
pid_arr=$(ps -ef | grep -v grep | grep "tongweb"|awk '{print $2}')
pid=''
for pid in ${pid_arr[@]}
do
    # 过滤掉端口不存在的进程
    port_str=$(netstat -ntlp | grep -w $pid)
    if [ -z "$port_str" ];then
        continue
    fi
    # 判断是不是java进程
    is_java=$(readlink /proc/$pid/exe | grep java)
    if [ -z "$is_java" ];then
     continue
    fi
    # 过滤掉蓝鲸sass 进程
    userId=$(ps -ef | grep tongweb | grep -w $pid | grep -v grep | awk '{print $1}')
    if [[ "$userId" == "apps" ]];then
        continue
    fi
    pid=$pid
done

# 未启动tongweb服务直接打印空{}
if [ -z "$pid" ]; then
  echo "{}"
  exit 0
fi

account=$(ps -o user= -p $pid)
# TongWeb 安装路径
tongweb_home=$(ls -l /proc/$pid/cwd | awk '{print $NF}' | awk -F"/bin" '{print $1}')
bin_path="$tongweb_home/bin"
log_path="$tongweb_home/logs"

# 获取 TongWeb 监听端口（从tongweb.xml中找）
config_path=$tongweb_home'/conf/tongweb.xml'
xml_content=$(cat $config_path)
listen_port=$(echo "$xml_content" |grep tong-http-listener | grep port | grep -oP '(?<= port=")[^"]+')
[ -z "$listen_port" ] && listen_port=8088  # 默认为 8088

# 获取 TongWeb 版本
if [ -f "$log_path/server.log" ]; then
  version=$(grep -i 'Product Version' "$log_path/server.log" | head -1 | grep -oP '\d+\.\d+')
else
  version=$(bash $Ttongweb_home/bin/version.sh | grep -oP '(?<=TW_Version_Number=)[^ ]+')
fi

cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline)
java_home=$(echo "$cmdline" | grep -oP '\/.*?\/java' | head -1 | sed 's/\/bin\/java//')
java_version=$("$java_home/bin/java" -version 2>&1 | awk -F '"' '/version/ {print $2}' | awk -F'_' '{print $1}')

xms=$(echo "$cmdline" | grep -oP '(?<=-Xms)[^ ]*')
xmx=$(echo "$cmdline" | grep -oP '(?<=-Xmx)[^ ]*')
output=$(jcmd "$pid" GC.heap_info 2>/dev/null)
capacity_kb=$(echo "$output" | grep 'Metaspace' | awk '{print $5}' | sed 's/,$//')
reserved_kb=$(echo "$output" | grep 'Metaspace' | awk '{print $9}')

# 拼接实例名
bk_inst_name=$bk_host_innerip-tongweb-$listen_port

# 输出 JSON 结构
json_template='{"inst_name": "%s", "ip_addr": "%s", "port": "%s", "version": "%s", "bin_path": "%s", "log_path": "%s", "java_version": "%s", "xms": "%s", "xmx": "%s", "metaspace_size": "%s", "max_metaspace_size": "%s", "bootstrap_path": "%s", "account": "%s"}'
json=$(printf "$json_template" \
    "$bk_inst_name" \
    "$bk_host_innerip" \
    "$listen_port" \
    "$version" \
    "$bin_path" \
    "$log_path" \
    "$java_version" \
    "$xms" \
    "$xmx" \
    "$capacity_kb" \
    "$reserved_kb" \
    "$tongweb_home" \
    "$account")

echo "$json"
