"""内置巡检预填的三条 SELECT。输入是一份作业信封，或 windows/linux 两个信封。"""

from __future__ import annotations

_EMPTY_HOST = (
    '{"hostname":"","os_version":"","architecture":"","uptime_hours":"",' '"cpu_cores":"","memory_total_gb":"","top_cpu":"","top_memory":""}'
)

_CTE = """
source_rows AS (
  SELECT 0 AS src, CAST(item.key AS INTEGER) AS ord, item.value AS row
  FROM input, json_each(json_extract(input.payload, '$.data')) AS item
  WHERE json_type(input.payload, '$.data') = 'array'
  UNION ALL
  SELECT 1, CAST(item.key AS INTEGER), item.value
  FROM input, json_each(json_extract(input.payload, '$.windows.data')) AS item
  WHERE COALESCE(json_type(input.payload, '$.data'), '') != 'array'
  UNION ALL
  SELECT 2, CAST(item.key AS INTEGER), item.value
  FROM input, json_each(json_extract(input.payload, '$.linux.data')) AS item
  WHERE COALESCE(json_type(input.payload, '$.data'), '') != 'array'
),
annotated AS (
  SELECT
    source_rows.src AS src,
    source_rows.ord AS host_ord,
    CAST(metric.key AS INTEGER) AS metric_ord,
    json_set(
      metric.value,
      '$.display_name',
      CASE
        WHEN json_extract(metric.value, '$.display_name') IS NULL
          OR json_extract(metric.value, '$.display_name') = ''
          THEN COALESCE(json_extract(metric.value, '$.metric_name'), '')
        ELSE json_extract(metric.value, '$.display_name')
      END,
      '$.value_text',
      CASE
        WHEN COALESCE(json_extract(metric.value, '$.unit'), '') = 'bool'
          THEN COALESCE(json_extract(metric.value, '$.detail'), '')
        WHEN trim(COALESCE(CAST(json_extract(metric.value, '$.value') AS TEXT), '')) = '' THEN ''
        ELSE (
          CASE
            WHEN CAST(json_extract(metric.value, '$.value') AS REAL)
              = CAST(CAST(json_extract(metric.value, '$.value') AS REAL) AS INTEGER)
              THEN CAST(CAST(CAST(json_extract(metric.value, '$.value') AS REAL) AS INTEGER) AS TEXT)
            ELSE printf('%g', CAST(json_extract(metric.value, '$.value') AS REAL))
          END
        ) || (
          CASE COALESCE(json_extract(metric.value, '$.unit'), '')
            WHEN '%' THEN '%' WHEN 'days' THEN '天'
            ELSE COALESCE(json_extract(metric.value, '$.unit'), '')
          END
        )
      END,
      '$.warning_line',
      CASE
        WHEN COALESCE(json_extract(metric.value, '$.unit'), '') = 'bool' THEN '—'
        WHEN json_type(metric.value, '$.warning_threshold') NOT IN ('integer', 'real')
          OR json_type(metric.value, '$.critical_threshold') NOT IN ('integer', 'real') THEN '—'
        WHEN CAST(json_extract(metric.value, '$.warning_threshold') AS REAL) = 0
          AND CAST(json_extract(metric.value, '$.critical_threshold') AS REAL) = 0 THEN '—'
        ELSE '≥' || (
          CASE
            WHEN CAST(json_extract(metric.value, '$.warning_threshold') AS REAL)
              = CAST(CAST(json_extract(metric.value, '$.warning_threshold') AS REAL) AS INTEGER)
              THEN CAST(CAST(CAST(json_extract(metric.value, '$.warning_threshold') AS REAL) AS INTEGER) AS TEXT)
            ELSE printf('%g', CAST(json_extract(metric.value, '$.warning_threshold') AS REAL))
          END
        ) || (
          CASE COALESCE(json_extract(metric.value, '$.unit'), '')
            WHEN '%' THEN '%' WHEN 'days' THEN '天'
            ELSE COALESCE(json_extract(metric.value, '$.unit'), '')
          END
        )
      END,
      '$.critical_line',
      CASE
        WHEN COALESCE(json_extract(metric.value, '$.unit'), '') = 'bool' THEN '—'
        WHEN json_type(metric.value, '$.warning_threshold') NOT IN ('integer', 'real')
          OR json_type(metric.value, '$.critical_threshold') NOT IN ('integer', 'real') THEN '—'
        WHEN CAST(json_extract(metric.value, '$.warning_threshold') AS REAL) = 0
          AND CAST(json_extract(metric.value, '$.critical_threshold') AS REAL) = 0 THEN '—'
        ELSE '≥' || (
          CASE
            WHEN CAST(json_extract(metric.value, '$.critical_threshold') AS REAL)
              = CAST(CAST(json_extract(metric.value, '$.critical_threshold') AS REAL) AS INTEGER)
              THEN CAST(CAST(CAST(json_extract(metric.value, '$.critical_threshold') AS REAL) AS INTEGER) AS TEXT)
            ELSE printf('%g', CAST(json_extract(metric.value, '$.critical_threshold') AS REAL))
          END
        ) || (
          CASE COALESCE(json_extract(metric.value, '$.unit'), '')
            WHEN '%' THEN '%' WHEN 'days' THEN '天'
            ELSE COALESCE(json_extract(metric.value, '$.unit'), '')
          END
        )
      END,
      '$.status_text',
      CASE json_extract(metric.value, '$.health_status')
        WHEN 'CRITICAL' THEN '严重'
        WHEN 'WARNING' THEN '告警'
        WHEN 'NORMAL' THEN '正常'
        ELSE COALESCE(json_extract(metric.value, '$.health_status'), '')
      END
    ) AS metric
  FROM source_rows, json_each(
    CASE
      WHEN json_type(source_rows.row, '$.result.metrics') = 'array'
        THEN json_extract(source_rows.row, '$.result.metrics')
      ELSE '[]'
    END
  ) AS metric
  WHERE json_type(source_rows.row) = 'object' AND json_type(metric.value) = 'object'
),
host_stats AS (
  SELECT
    source_rows.src AS src,
    source_rows.ord AS host_ord,
    source_rows.row AS row,
    (
      SELECT COUNT(*) FROM annotated
      WHERE annotated.src = source_rows.src
        AND annotated.host_ord = source_rows.ord
        AND json_extract(annotated.metric, '$.health_status') = 'CRITICAL'
    ) AS critical_count,
    (
      SELECT COUNT(*) FROM annotated
      WHERE annotated.src = source_rows.src
        AND annotated.host_ord = source_rows.ord
        AND json_extract(annotated.metric, '$.health_status') = 'WARNING'
    ) AS warning_count,
    (
      SELECT COUNT(*) FROM annotated
      WHERE annotated.src = source_rows.src
        AND annotated.host_ord = source_rows.ord
        AND json_extract(annotated.metric, '$.health_status') = 'NORMAL'
    ) AS normal_count,
    (
      SELECT COUNT(*) FROM annotated
      WHERE annotated.src = source_rows.src AND annotated.host_ord = source_rows.ord
    ) AS metric_count,
    CASE
      WHEN json_type(source_rows.row) != 'object'
        OR UPPER(COALESCE(json_extract(source_rows.row, '$.status'), '')) != 'SUCCESS' THEN NULL
      WHEN (
        SELECT COUNT(*) FROM annotated
        WHERE annotated.src = source_rows.src
          AND annotated.host_ord = source_rows.ord
          AND json_extract(annotated.metric, '$.health_status') = 'CRITICAL'
      ) > 0 THEN 'critical'
      WHEN (
        SELECT COUNT(*) FROM annotated
        WHERE annotated.src = source_rows.src
          AND annotated.host_ord = source_rows.ord
          AND json_extract(annotated.metric, '$.health_status') = 'WARNING'
      ) > 0 THEN 'warning'
      ELSE 'healthy'
    END AS bucket
  FROM source_rows
)
"""


def _summary_sql() -> str:
    return f"""
WITH {_CTE}
SELECT json_patch(
  CASE
    WHEN json_type((SELECT payload FROM input), '$.summary') = 'object'
      THEN json_extract((SELECT payload FROM input), '$.summary')
    ELSE json_object()
  END,
  json_object(
    'total', (SELECT COUNT(*) FROM host_stats),
    'succeeded', (SELECT COUNT(*) FROM host_stats WHERE bucket IS NOT NULL),
    'failed', (SELECT COUNT(*) FROM host_stats WHERE bucket IS NULL),
    'critical_hosts', (SELECT COUNT(*) FROM host_stats WHERE bucket = 'critical'),
    'warning_hosts', (SELECT COUNT(*) FROM host_stats WHERE bucket = 'warning'),
    'healthy_hosts', (SELECT COUNT(*) FROM host_stats WHERE bucket = 'healthy'),
    'collected_at', COALESCE((
      SELECT formatted FROM (
        SELECT
          src,
          host_ord,
          substr(
            CASE
              WHEN instr(collected, '+') > 0 THEN substr(collected, 1, instr(collected, '+') - 1)
              ELSE collected
            END,
            1,
            19
          ) AS formatted
        FROM (
          SELECT
            src,
            host_ord,
            replace(replace(trim(COALESCE(json_extract(row, '$.result.collected_at'), '')), 'T', ' '), 'Z', '') AS collected
          FROM host_stats
          WHERE json_type(row) = 'object'
        )
      )
      WHERE formatted != ''
      ORDER BY src, host_ord
      LIMIT 1
    ), '')
  )
)
"""


def _metric_summary_sql() -> str:
    return f"""
WITH {_CTE}
SELECT COALESCE((
  SELECT json_group_array(json_object(
    'category', category,
    'name', name,
    'warning_line', warning_line,
    'critical_line', critical_line,
    'critical_count', critical_count,
    'warning_count', warning_count,
    'normal_count', normal_count,
    'conclusion', conclusion
  ))
  FROM (
    SELECT
      COALESCE(json_extract(metric, '$.category'), '') AS category,
      COALESCE(json_extract(metric, '$.display_name'), '') AS name,
      COALESCE(json_extract(metric, '$.unit'), '') AS unit,
      CASE
        WHEN CAST(json_extract(metric, '$.warning_threshold') AS REAL)
          = CAST(CAST(json_extract(metric, '$.warning_threshold') AS REAL) AS INTEGER)
          THEN CAST(CAST(CAST(json_extract(metric, '$.warning_threshold') AS REAL) AS INTEGER) AS TEXT)
        ELSE printf('%g', CAST(json_extract(metric, '$.warning_threshold') AS REAL))
      END AS warning_number,
      CASE
        WHEN CAST(json_extract(metric, '$.critical_threshold') AS REAL)
          = CAST(CAST(json_extract(metric, '$.critical_threshold') AS REAL) AS INTEGER)
          THEN CAST(CAST(CAST(json_extract(metric, '$.critical_threshold') AS REAL) AS INTEGER) AS TEXT)
        ELSE printf('%g', CAST(json_extract(metric, '$.critical_threshold') AS REAL))
      END AS critical_number,
      COALESCE(json_extract(metric, '$.warning_line'), '—') AS warning_line,
      COALESCE(json_extract(metric, '$.critical_line'), '—') AS critical_line,
      SUM(CASE WHEN json_extract(metric, '$.health_status') = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_count,
      SUM(CASE WHEN json_extract(metric, '$.health_status') = 'WARNING' THEN 1 ELSE 0 END) AS warning_count,
      SUM(CASE WHEN json_extract(metric, '$.health_status') = 'NORMAL' THEN 1 ELSE 0 END) AS normal_count,
      CASE
        WHEN SUM(CASE WHEN json_extract(metric, '$.health_status') = 'CRITICAL' THEN 1 ELSE 0 END) > 0
          OR SUM(CASE WHEN json_extract(metric, '$.health_status') = 'WARNING' THEN 1 ELSE 0 END) > 0
          THEN '需关注'
        ELSE '健康'
      END AS conclusion
    FROM annotated
    GROUP BY 1, 2, 3, 4, 5
    ORDER BY
      CASE
        WHEN SUM(CASE WHEN json_extract(metric, '$.health_status') = 'CRITICAL' THEN 1 ELSE 0 END) > 0 THEN 0
        WHEN SUM(CASE WHEN json_extract(metric, '$.health_status') = 'WARNING' THEN 1 ELSE 0 END) > 0 THEN 1
        ELSE 2
      END,
      CASE COALESCE(json_extract(metric, '$.category'), '')
        WHEN '计算' THEN 0 WHEN '内存' THEN 1 WHEN '磁盘' THEN 2 WHEN '网络' THEN 3
        WHEN '系统健康' THEN 4 WHEN '进程热点' THEN 5 WHEN '基础服务' THEN 6
        WHEN '安全浅检' THEN 7 WHEN '更新账龄' THEN 8 ELSE 9
      END,
      COALESCE(json_extract(metric, '$.display_name'), '')
  )
), json_array())
"""


def _metric_array(status: str | None) -> str:
    where = ""
    if status is not None:
        where = f" AND json_extract(annotated.metric, '$.health_status') = '{status}'"
    return f"""json(COALESCE((
      SELECT json_group_array(json(annotated.metric) ORDER BY annotated.metric_ord)
      FROM annotated
      WHERE annotated.src = stats.src AND annotated.host_ord = stats.host_ord{where}
    ), '[]'))"""


def _data_sql() -> str:
    metrics = _metric_array(None)
    critical = _metric_array("CRITICAL")
    warning = _metric_array("WARNING")
    normal = _metric_array("NORMAL")
    return f"""
WITH {_CTE}
SELECT COALESCE(json_group_array(json(host_json) ORDER BY src, host_ord), json_array())
FROM (
  SELECT
    stats.src AS src,
    stats.host_ord AS host_ord,
    CASE
      WHEN json_type(stats.row) != 'object' THEN stats.row
      ELSE json_set(
        stats.row,
        '$.result',
        json_set(
          CASE
            WHEN json_type(stats.base_result, '$.host') = 'object' THEN stats.base_result
            ELSE json_set(stats.base_result, '$.host', json('{_EMPTY_HOST}'))
          END,
          '$.metrics', {metrics},
          '$.critical', {critical},
          '$.warning', {warning},
          '$.normal', {normal},
          '$.critical_count', stats.critical_count,
          '$.warning_count', stats.warning_count,
          '$.normal_count', stats.normal_count,
          '$.metric_count', stats.metric_count
        )
      )
    END AS host_json
  FROM (
    SELECT
      host_stats.*,
      CASE
        WHEN json_type(host_stats.row, '$.result') = 'object' THEN json_extract(host_stats.row, '$.result')
        ELSE json_object(
          'collected_at', '',
          'conclusion', COALESCE(
            NULLIF(json_extract(row, '$.error'), ''),
            NULLIF(json_extract(row, '$.status'), ''),
            ''
          ),
          'host', json('{_EMPTY_HOST}'),
          'metrics', json_array(),
          'critical', json_array(),
          'warning', json_array(),
          'normal', json_array()
        )
      END AS base_result
    FROM host_stats
  ) AS stats
)
"""


def health_summary_queries() -> list[dict[str, str]]:
    return [
        {"name": "summary", "sql": _summary_sql().strip()},
        {"name": "metric_summary", "sql": _metric_summary_sql().strip()},
        {"name": "data", "sql": _data_sql().strip()},
    ]


def health_transform_input(data: object) -> dict[str, object]:
    return {"data": data, "queries": health_summary_queries(), "timeout_seconds": 30}
