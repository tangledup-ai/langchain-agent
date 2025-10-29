from langsmith import Client
from loguru import logger


DATASET_NAME = "dev_langagent"

examples = [
    {
        "inputs": {"text": "介绍一下自己"},
        "outputs": {"answer": "我是小盏，是一个点餐助手"}
    },
    {
        "inputs": {"text": "用retrieve查询光予尘然后介绍"},
        "outputs": {"answer": "茉莉绿茶为底，清冽茶香中漫出玫珑蜜瓜的绵甜与凤梨的明亮果香，层次鲜活；顶部白柚茉莉泡沫轻盈漫过舌尖，带着微酸的清新感，让整体风味更显灵动",
                    "tool_use": ["retrieve"]}
    },
    {
        "inputs": {"text": ["我叫Steve",
                            "我叫什么名字?"]},   # list for conversation
        "outputs": {"answer": "你叫Steve"}
    }
]

cli = Client()

try:
    dataset = cli.read_dataset(dataset_name=DATASET_NAME)
    logger.info("read dataset")
except:
    dataset = cli.create_dataset(dataset_name=DATASET_NAME)
    logger.info("created dataset")

cli.create_examples(
    dataset_id=dataset.id,
    examples=examples
)