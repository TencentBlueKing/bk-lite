from apps.workflow.services.data_transform import DataTransformError, run_data_transform


def execute(inputs: dict) -> dict:
    try:
        return run_data_transform(inputs.get("data"), inputs.get("queries"), inputs.get("timeout_seconds"))
    except DataTransformError as error:
        raise ValueError(str(error)) from error
