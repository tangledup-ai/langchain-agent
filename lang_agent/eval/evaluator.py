from dataclasses import dataclass, field
from typing import Type, Literal
import tyro
from loguru import logger
import functools
import os
import os.path as osp
import glob
import pandas as pd

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

    dataset_name:Literal["Toxic Queries"] = "dev_langagent"
    """name of the dataset to evaluate"""

    log_dir:str = "logs"

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
        self.validator:Validator = self.config.validator_config.setup()
        self.dataset = self.cli.read_dataset(dataset_name=self.config.dataset_name)


    def evaluate(self):
        logger.info("running experiment")
        
        inp_fnc = self.validator.get_inp_fnc(self.config.dataset_name)
        runnable = functools.partial(inp_fnc, pipeline=self.pipeline)

        self.result = self.cli.evaluate(
            runnable,
            data=self.dataset.name,
            evaluators=self.validator.get_val_fnc(self.config.dataset_name),
            experiment_prefix=self.config.experiment_prefix,
            description=self.config.experiment_desc,
            max_concurrency=4,
            upload_results=False
        )


    def save_results(self):
        os.makedirs(self.config.log_dir, exist_ok=True)

        assert hasattr(self, "result"), "NO RESULTS, run evaluate() before saving results"

        head_path = osp.join(self.config.log_dir, f"{self.dataset.name}-{self.config.experiment_prefix}")
        n_exp = len(glob.glob(f"{head_path}*"))
        exp_save_f = f"{head_path}-{n_exp}.csv"

        df = self.result.to_pandas()
        logger.info(f"saving experiment results to: {exp_save_f}")
        df.to_csv(exp_save_f, index=False)

        metric_col = [e for e in df.columns if "feedback" in e]

        df_curr_m = df[metric_col].mean().to_frame().T
        df_curr_m.index = [f'{osp.basename(head_path)}-{n_exp}']

        metric_f = osp.join(self.config.log_dir, "0_exp_metrics.csv")  # start with 0 for first file in folder
        if osp.exists(metric_f):
            df_m = pd.read_csv(metric_f, index_col=0)
            df_m = pd.concat([df_m, df_curr_m])
        else:
            df_m = df_curr_m
        
        df_m.to_csv(metric_f)

        self.config.save_config(f"{head_path}-{n_exp}.yml")


