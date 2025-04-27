from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI


class Metrics:
    @staticmethod
    def get_metrics(query):
        """查询指标信息"""
        return VictoriaMetricsAPI().query(query)

    @staticmethod
    def get_metrics_range(query, start, end, step):
        """查询指标（范围）"""
        return VictoriaMetricsAPI().query_range(query, start, end, step)
