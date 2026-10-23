"""Technical checks of the run's candidate; it never reads the study's final test."""

import logging
import sys

import hydra
from omegaconf import DictConfig

from ..utils.hypotrail import steps
from ..utils.hypotrail.config import freeze
from ..utils.hypotrail.errors import ProjectError
from ..utils.tracking import MLFlowDummy


def evaluate_model(frozen: dict) -> dict:
    """Verify, reload and compare the candidate; no generalisation metric is produced."""
    return steps.evaluate(frozen)


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
        result = evaluate_model(frozen)
        steps.log_json(result)
        mlf.end_run()
    except ProjectError as error:
        logging.error("%s", error.to_json())
        sys.exit(2)


if __name__ == "__main__":
    main()
