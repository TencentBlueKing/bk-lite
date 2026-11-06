#!/bin/bash
host_innerip=$(hostname -I | awk '{print $1}')
# 获取进程端口号
Get_Port_Join_Str(){
    port_arr_str=$(netstat -ntlp | grep $1 |awk '{print $4}'|awk -F ':' '{print $NF}'|sed 's/ *$//g'|sed 's/^ *//g'|sort|uniq)
    if [ -z "$port_arr_str" ];then
        continue
    fi
    port_str=""
    for port in ${port_arr_str[@]}
    do
        if [ -n "$port_str" ];then
            port_str=${port_str},${port}
        else
            port_str=${port}
        fi
    done
}
# 获取进程pid
Get_Mongo_Pid(){
    i=0
    mongo_pid=()
    pid_arr=$(ps -ef | grep -v grep | grep $1 |awk '{print $2}')
    for pid in ${pid_arr[@]}
    do
     # 过滤掉端口不存在的进程
        port_str=$(netstat -ntlp | grep -w $pid)
        if [ -z "$port_str" ];then
            continue
        fi
        # 过滤掉蓝鲸sass进程
        userId=$(ps -ef | grep $1 | grep -w $pid | grep -v grep | awk '{print $1}')
        if [[ "$userId" == "apps" ]];then
            continue
        fi
         # 过滤掉不是mongo的进程
         is_mongo=$($(readlink /proc/$pid/exe) -v 2>/dev/null|grep -i mongo)
         if [ -z "$is_mongo" ];then
        	continue
        fi
         # 筛选后的pid
        mongo_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

Cover_Mongo(){
    conditions=(mongo)
    inst_name_array=()
    for condition in ${conditions[@]}
    do
        Get_Mongo_Pid $condition
        for pid in ${mongo_pid[@]}
        do
            Get_Port_Join_Str $pid
            exe_path=$(readlink /proc/$pid/exe)
            inst_name="$host_innerip-mongodb-$port_str"
            if [[ " ${inst_name_array[*]} " =~ " ${inst_name} " ]];then
                continue
            fi
            bin_path=$(dirname $exe_path)
            mongo_path="$bin_path/mongo"
            if [[ ! -f "$mongo_path" ]]; then
                mongo_path=""
            fi
            inst_name_array[${#inst_name_array[@]}]=$inst_name
            version=$($exe_path --version | grep -i "db version" | awk '{print $3}' | sed 's/^v//')
            cmd_expr="cat /proc/$pid/cmdline"
            config=$($cmd_expr | tr '\0' ' ' | grep -oP '(?<=--config)[^-]+|(?<=-f)[^-]+'|awk '{print $1}')
            if [[ ! -f "$config" ]]; then
                config="/etc/mongod.conf"
            fi

            # 最大并发连接数采集
            max_incoming_conn=$(cat $config 2>/dev/null | grep -v '^#' | awk '/^maxIncomingConnections:/ {print $2}' | sed 's/[;]//g')
            if [ -z "$max_incoming_conn" ]; then
                max_incoming_conn="default:819"
            fi

            # 数据库角色采集。口令只来自进程环境，不进入命令参数或 eval 文本。
            database_role=$(query_mongo_role "$port_str" "$mongo_path")

            fork=$(cat $config 2>/dev/null | grep -v '^#'|awk '/fork:/ {print $2}')
            system_log=$(cat $config 2>/dev/null | grep -v '^#'| awk '/systemLog:/,/\}/' | awk '/path:/ {print $2}')
            db_path=$(cat $config 2>/dev/null | grep -v '^#'  | awk '/storage:/,/\}/' | awk '/dbPath:/ {print $2}')

            json_str=$(printf '{"inst_name":"%s","ip_addr":"%s","obj_id":"mongodb","bin_path":"%s","mongo_path":"%s","port":"%s","version":"%s","config":"%s","fork":"%s","system_log":"%s","db_path":"%s","max_incoming_conn":"%s","database_role":"%s"}' \
            "$inst_name" "$host_innerip" "$bin_path" "$mongo_path" "$port_str" "$version" "$config"  "$fork" "$system_log" "$db_path" "$max_incoming_conn" "$database_role")
            echo $json_str
            MONGO_HOST_FOUND=1
        done
    done
}

query_mongo_role() {
    local port="$1"
    local mongo_bin="$2"
    local output role client
    if [[ -z "$port" ]]; then
        return 0
    fi
    if [[ -n "${MONGO_USER:-}" && -n "${MONGO_PASSWORD:-}" ]]; then
        client="$mongo_bin"
        if command -v mongosh >/dev/null 2>&1; then
            client=$(command -v mongosh)
        fi
        [[ -z "$client" || ! -x "$client" ]] && return 0
        output=$("$client" --quiet --port "$port" --eval 'try { db.getSiblingDB(process.env.MONGO_AUTH_DB || "admin").auth(process.env.MONGO_USER, process.env.MONGO_PASSWORD); const st = rs.status(); const me = (st.members || []).find(function(m){ return m.self; }); if (me && me.stateStr) { print("role " + me.stateStr); } } catch (e) { if (/not running with --replSet|no replset config/i.test(String(e))) { print("role standalone"); } }' 2>/dev/null)
        role=$(printf '%s\n' "$output" | grep -i 'role' | awk '{print $2}' | head -n1)
        printf '%s' "$role"
        return 0
    fi
    [[ -z "$mongo_bin" || ! -x "$mongo_bin" ]] && return 0
    output=$("$mongo_bin" --port "$port" --eval "rs.status()" 2>/dev/null)
    role=$(printf '%s\n' "$output" | grep -i 'role' | awk '{print $2}' | head -n1)
    if [[ -z "$role" ]] && printf '%s\n' "$output" | grep -qi 'not running with --replSet'; then
        role="standalone"
    fi
    printf '%s' "$role"
}

docker_mongo_env_args() {
    local args=""
    [[ -n "${MONGO_USER:-}" ]] && args="$args -e MONGO_USER"
    [[ -n "${MONGO_PASSWORD:-}" ]] && args="$args -e MONGO_PASSWORD"
    [[ -n "${MONGO_AUTH_DB:-}" ]] && args="$args -e MONGO_AUTH_DB"
    printf '%s' "$args"
}

emit_mongo_json() {
    printf '{"inst_name":"%s","ip_addr":"%s","obj_id":"mongodb","bin_path":"%s","mongo_path":"%s","port":"%s","version":"%s","config":"%s","fork":"%s","system_log":"%s","db_path":"%s","max_incoming_conn":"%s","database_role":"%s"}\n' \
        "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}"
}

discover_mongo_containers() {
    command -v docker >/dev/null 2>&1 || return 0
    local id mapping cport hport exe version config config_body max_incoming_conn fork system_log db_path database_role bin_path mongo_client env_args
    while read -r id; do
        [[ -z "$id" ]] && continue
        exe=$(docker exec "$id" sh -c 'command -v mongod' 2>/dev/null) || continue
        case "$exe" in
            /*mongod) ;;
            *) continue ;;
        esac
        bin_path=$(dirname "$exe")
        mongo_client="$bin_path/mongosh"
        [[ -x "$mongo_client" ]] || mongo_client="$bin_path/mongo"
        version=$(docker exec "$id" "$exe" --version 2>/dev/null | grep -i "db version" | awk '{print $3}' | sed 's/^v//' | head -n1)
        [[ -z "$version" ]] && continue
        config=$(docker exec "$id" sh -c 'tr "\0" " " </proc/1/cmdline 2>/dev/null' | grep -oE '(--config|-f) [^ ]+' | awk '{print $2}' | head -n1)
        [[ -z "$config" ]] && config="/etc/mongod.conf"
        case "$config" in
            *[!A-Za-z0-9._/-]*) config="/etc/mongod.conf" ;;
        esac
        config_body=$(docker exec "$id" sh -c "grep -v '^#' '$config' 2>/dev/null" || true)
        max_incoming_conn=$(printf '%s\n' "$config_body" | awk '/^maxIncomingConnections:/ {print $2}' | sed 's/[;]//g' | head -n1)
        [[ -z "$max_incoming_conn" ]] && max_incoming_conn="default:819"
        fork=$(printf '%s\n' "$config_body" | awk '/^fork:/ {print $2}' | head -n1)
        system_log=$(printf '%s\n' "$config_body" | awk '/systemLog:/,/}/' | awk '/path:/ {print $2}' | head -n1)
        db_path=$(printf '%s\n' "$config_body" | awk '/storage:/,/}/' | awk '/dbPath:/ {print $2}' | head -n1)
        while read -r mapping; do
            cport=$(printf '%s\n' "$mapping" | sed -n 's#^\([0-9][0-9]*\)/tcp -> .*:\([0-9][0-9]*\)$#\1#p')
            hport=$(printf '%s\n' "$mapping" | sed -n 's#^\([0-9][0-9]*\)/tcp -> .*:\([0-9][0-9]*\)$#\2#p')
            [[ -z "$hport" ]] && continue
            env_args=$(docker_mongo_env_args)
            database_role=$(docker exec $env_args "$id" sh -c 'command -v mongosh || command -v mongo' 2>/dev/null | head -n1)
            if [[ -n "$database_role" ]]; then
                database_role=$(docker exec $env_args "$id" "$database_role" --quiet --port "$cport" --eval 'try { if (process.env.MONGO_USER && process.env.MONGO_PASSWORD) { db.getSiblingDB(process.env.MONGO_AUTH_DB || "admin").auth(process.env.MONGO_USER, process.env.MONGO_PASSWORD); } const st = rs.status(); const me = (st.members || []).find(function(m){ return m.self; }); if (me && me.stateStr) { print("role " + me.stateStr); } } catch (e) { if (/not running with --replSet|no replset config/i.test(String(e))) { print("role standalone"); } }' 2>/dev/null | grep -i 'role' | awk '{print $2}' | head -n1)
            fi
            emit_mongo_json "$host_innerip-mongodb-$hport" "$host_innerip" "$bin_path" "$mongo_client" "$hport" "$version" "$config" "$fork" "$system_log" "$db_path" "$max_incoming_conn" "$database_role"
            break
        done < <(docker port "$id" 2>/dev/null)
    done < <(docker ps -q 2>/dev/null)
}

Cover_Mongo
if [[ "${MONGO_HOST_FOUND:-0}" != "1" ]]; then
    discover_mongo_containers
fi

            
