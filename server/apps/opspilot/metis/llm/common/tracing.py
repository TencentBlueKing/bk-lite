import mlflow
from mlflow.tracing import configure

def setup_llm_tracing(mlflow_tracking_uri, experiment_name):
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(experiment_name)

    def pii_filter(span):
        # 屏蔽 inputs 里的 *_api_key / *token* 等字段
        if span.inputs:
            masked = dict(span.inputs)
            for k in list(masked.keys()):
                if any(s in k.lower() for s in ["api_key", "token", "secret", "password"]):
                    masked[k] = "[REDACTED]"
            span.set_inputs(masked)

        # 屏蔽 attributes 里的敏感键（有些库会把 key 放在属性里）
        for attr_k in list(span.attributes.keys()):
            if any(s in attr_k.lower() for s in ["api_key", "token", "secret", "password"]):
                span.set_attribute(attr_k, "[REDACTED]")

        # 如有需要，也可对 outputs 做同样处理
        if span.outputs and isinstance(span.outputs, dict):
            masked_out = dict(span.outputs)
            for k in list(masked_out.keys()):
                if any(s in k.lower() for s in ["api_key", "token", "secret", "password"]):
                    masked_out[k] = "[REDACTED]"
            span.set_outputs(masked_out)

    configure(span_processors=[pii_filter])
    mlflow.langchain.autolog()