#!/bin/bash
export LC_ALL=en_US.UTF-8

inst_list=$(more /etc/passwd | grep db2 | awk -F ':' '{print $1}')
if [[ -z "$inst_list" ]]; then
    echo "{}"
    exit 0
fi

function GetInfo(){
	inst_name=$1
	dbname=$2

  ip_addr={{bk_host_innerip}}
	port=$(su - $inst_name  -s /bin/bash -c "grep '$port_name' /etc/services" | awk -F ' ' '{print $2}' | awk -F '/' '{print $1}' )
	DB_VERSION=$(su - $inst_name -s /bin/bash -c "db2level" | grep -oP "(?<=DB2 ).*(\.)[0-9]\b")
	DB_PATCH=$DB_VERSION

  # 测试获取多端口
  PORT_LIST=$(cat /etc/services|grep DB2_$inst_name | awk '{print $2}' | awk -F '/' '{print $1}')
  PORT=${PORT_LIST[*]}

	DB_CHARSET=''
  HA_MODE='1'
  replication_managerole="4"
  replication_role="3"
	#高可用方式
  #1、Db2pd -cfinfo: 查看是不是purescale
  purescale_index=$(su - $inst_name -s /bin/bash -c" db2pd -cfinfo" | grep -c "CF Server (128)")
  if [ $purescale_index -gt 0 ]; then
    #节点CF判断
    ca_sever_index=$(ps -ef |grep -v grep |grep -c "ca-server")
    if [ $ca_sever_index -gt 0 ];then
      is_CF="true"
    else
      is_CF="false"
    fi
    # 节点membsers#判断
    membsers_index=$(ps -ef |grep db2sysc |grep idle |grep -oP '\(.*\)' |sort |awk '{printf $NF}' |grep "997)998)999)"| wc -l)
    if [ ${membsers_index} == "1" ];then
      is_membsers="true"
    else
      is_membsers="false"
    fi
    #replication_managerole数据库角色
    if [ $is_CF == "true" -a $is_membser == "true" ];then
      replication_managerole="3"
    elif [ $is_CF = "true" -a $is_membser == "false" ]; then
      replication_managerole="1"
    elif [ $is_CF = "false" -a $is_membser == "true" ]; then
      replication_managerole="2"
    else
      replication_managerole="4"
    fi

    is_purescale="true"
  else
    is_purescale="false"
  fi
  #循环数据库
  DB_CHARSET=$(su - $inst_name -s /bin/bash -c " db2 get db cfg for $dbname" | grep -i "Database code set" | awk '{print $(NF)}')
  hadr_index=$(su - $inst_name -s /bin/bash -c " db2pd -hadr -db $dbname" | grep "HADR_ROLE=" | wc -l)
  replication_primary=$(su - $inst_name -s /bin/bash -c " db2pd -hadr -db $dbname" | grep "HADR_ROLE = PRIMARY" | wc -l)
  replication_standby=$(su - $inst_name -s /bin/bash -c " db2pd -hadr -db $dbname" | grep "HADR_ROLE = STANDBY" | wc -l)

  if [ "$replication_primary" == "1" ]; then
    replication_role="1"
  elif [ "$replication_standby" == "1" ]; then
    replication_role="2"
  else
    replication_role="3"
  fi

  if [ $is_purescale == "true" ]; then
    HA_MODE="2"
  fi

  #TOD0 数据保护方式存储复制
  if [ "$hadr_index" == "1" ]; then
    data_protect_mode="2"
  else
    data_protect_mode="1"
  fi

	JSON_RETURN='{
    "inst_name":"'$ip_addr-db2'",
    "version":"'$DB_VERSION'",
    "db_patch":"'$DB_PATCH'",
    "db_name":"'$dbname'",
    "db_instance_name":"'$inst_name'",
    "ip_addr":"'$ip_addr'",
    "port":"'$PORT'",
    "db_character_set":"'$DB_CHARSET'",
    "ha_mode":"'$HA_MODE'",
    "replication_managerole":"'$replication_managerole'",
    "replication_role":"'$replication_role'",
    "data_protect_mode":"'$data_protect_mode'"
  }'
	echo $JSON_RETURN
}

for inst_name in ${inst_list[*]}
do
    DB_LIST=$(su - $inst_name -s /bin/bash -c "db2 list db directory" | egrep -i -B 4 'Directory entry type.*Indirect'| grep -i 'database name' | awk '{print $(NF)}')
    db_list=($DB_LIST)
    for db_name in ${db_list[*]}
    do
	    db_info=$(GetInfo "$inst_name" "$db_name")
	    echo $db_info
    done
done
