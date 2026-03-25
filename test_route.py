from lang_agent.pipeline import Pipeline, PipelineConfig
from lang_agent.graphs.routing import RoutingGraph
from loguru import logger
import sys

# logger.remove()
# logger.add(sys.stdout, level="INFO")

conf = PipelineConfig()
pipeline = conf.setup()
print("Pipeline instantiated.")

response = pipeline.chat('介绍一下我两最最好', as_stream=False, thread_id='test_2')
print('Response:', response)

response2 = pipeline.chat('我两最最好', as_stream=False, thread_id='test_3')
print('Response2:', response2)
