import tyro

from lang_agent.eval import Evaluator, EvaluatorConfig

def main(conf: EvaluatorConfig):
    evaluator: Evaluator = conf.setup()
    evaluator.evaluate()


if __name__ == "__main__":
    main(tyro.cli(EvaluatorConfig))