from langsmith import Client
from loguru import logger


DATASET_NAME = "xiao_zhan"

examples = [
    {
        "inputs": {"text": "今天有点热，推荐点茶喝一下"},
        "outputs": {"answer": None,
                    "tool_use": ["retrieve"]}
    },
    {
        "inputs": {"text": "有没有光予尘？"},
        "outputs": {"answer": "有的",
                    "tool_use": ["retrieve|get_resource"]}
    },
    {
        "inputs": {"text": "有没有关羽尘？"},
        "outputs": {"answer": "有的",
                    "tool_use": ["retrieve|get_resource"]}
    },
    {
        "inputs": {"text": ["我要购买一杯野星星",
                            "我要再加一杯"]},
        "outputs": {"answer": "你的野星星已经下单成功",
                    "tool_use": ["retrieve|get_resources",
                                 "start_shopping_session",
                                 "add_to_cart",
                                 "create_wechat_pay",
                                 "create_order_from_cart",
                                 "update_cart_item"]}
    },
    {
        "inputs": {"text": ["我要购买一杯野星星",
                            "我现在点了些什么？"]},
        "outputs": {"answer": "一杯野星星",
                    "tool_use": ["query_wechat_order"]}
    },
    {
        "inputs": {"text": ["我要购买三杯野星星",
                            "现在取消所有我定了的饮品"]},
        "outputs": {"answer": "取消成功",
                    "tool_use": ["clear_cart"]}
    },
    {
        "inputs": {"text": "你是谁？"},
        "outputs": {"answer": "小盏"}
    },
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