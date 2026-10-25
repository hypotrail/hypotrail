"""Fit a new candidate (rebuilt_candidate) with the study's selected recipe."""

import logging
import sys

import hydra
from omegaconf import DictConfig

from ..utils.hypotrail import steps
from ..utils.hypotrail.config import freeze
from ..utils.hypotrail.errors import from_exception
from ..utils.tracking import MLFlowDummy


def train_model(frozen: dict) -> dict:
    """Fit and capture the candidate through hypotrail_runtime; nothing is registered."""
    return steps.train(frozen)


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
        result = train_model(frozen)
        steps.log_json(result)
        mlf.end_run()
    except Exception as error:
        # A refusal of this project, of hypotrail_runtime (ContractError) or of the packager
        # (PackagingError) is printed as one JSON refusal line, exit code 2; anything else
        # is not a refusal and is raised (an internal error of the step).
        refusal = from_exception(error)
        if refusal is None:
            raise
        logging.error("%s", refusal.to_json())
        sys.exit(2)


if __name__ == "__main__":
    main()
