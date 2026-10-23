"""Materialise the recorded partitions of the development plan; no new split is drawn."""

import logging
import sys

from omegaconf import DictConfig

import hydra

from ..utils.hypotrail import steps
from ..utils.hypotrail.config import freeze
from ..utils.hypotrail.errors import ProjectError
from ..utils.tracking import MLFlowDummy


def split_data(frozen: dict) -> dict:
    """Write each recorded partition and check its key hash."""
    return steps.split(frozen)


@hydra.main(version_base=None, config_path="../../conf", config_name="config")
def main(cfg: DictConfig) -> None:
    """Freeze the configuration, then run the step.

    Args:
    ----
        cfg (DictConfig): run configuration as defined in the path.

    """
    try:
        frozen = freeze(cfg)
        if frozen["config"]["mlflow_tracking"]:
            import mlflow

            mlf = mlflow
        else:
            mlf = MLFlowDummy()
        mlf.log_param("hypotrail_scientific_sha256", frozen["scientific_sha256"])
        result = split_data(frozen)
        steps.log_json(result)
        mlf.end_run()
    except ProjectError as error:
        logging.error("%s", error.to_json())  # noqa: TRY400
        sys.exit(2)


if __name__ == "__main__":
    main()
