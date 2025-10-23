from dataclasses import dataclass, field
from typing import Type, Literal
import tyro
from loguru import logger

from lang_agent.config import InstantiateConfig
from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.eval.validator import ValidatorConfig, Validator

from langsmith import Client

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class EvaluatorConfig(InstantiateConfig):
    _target: Type = field(default_factory=lambda:Evaluator)

    experiment_prefix:str = "simple test"
    """name of experiment"""

    experiment_desc:str = "testing if this works or not"
    """describe the experiment"""

    dataset_name:Literal["Toxic Queries"] = "Toxic Queries"
    """name of the dataset to evaluate"""

    pipe_config: PipelineConfig = field(default_factory=PipelineConfig)

    validator_config: ValidatorConfig = field(default_factory=ValidatorConfig)


class Evaluator:
    def __init__(self, config: EvaluatorConfig):
        self.config = config

        self.populate_modules()
    
    def populate_modules(self):
        logger.info("preparing to run experiment")
        self.pipeline:Pipeline = self.config.pipe_config.setup()
        self.cli = Client()
        self.validator:Validator = self.config.validator_config.setup(
                                                dataset_name=self.config.dataset_name
                                            )
        self.dataset = self.cli.read_dataset(dataset_name=self.config.dataset_name)


    def evaluate(self):
        logger.info("running experiment")
        self.result = self.cli.evaluate(
            self.pipeline.chat,
            data=self.dataset.name,
            evaluators=[self.validator.get_val_fnc(self.config.dataset_name)],
            experiment_prefix=self.config.experiment_prefix,
            description=self.config.experiment_desc
        )
    

        


