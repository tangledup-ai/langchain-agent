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
        "outputs": {"answer": "有",
                    "tool_use": ["retrieve|get_dishes"]}
    },
    {
        "inputs": {"text": "有没有关羽尘？"},
        "outputs": {"answer": "有",
                    "tool_use": ["retrieve|get_dishes"]}
    },
    {
        "inputs": {"text": ["我要购买一杯野星星",
                            "我要再加一杯"]},
        "outputs": {"answer": "你的野星星已经下单成功",
                    "tool_use": ["retrieve|get_dishes",
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
    {
        "inputs": {"text":"介绍下你的形象"},
        "outputs": {"answer":"小盏是一只中式茶盖碗，名字来源半盏新青年茶馆。有个蓝色鼻子"}
    },
    {
        "inputs": {"text":"介绍下你的公司"},
        "outputs": {"answer":"叠加态 AI（TANGLED UP AI）是一家专注于 AI 技术应用的公司，由一帮名校和海归创始人创立，致力于将 AI 技术落地到实际场景中。2023年3月成立，专注于AI前沿应用拓展，是云南地区在该领域的新兴力量"}
    },
    {
        "inputs": {"text":"介绍下你的品牌"},
        "outputs": {"answer":"半盏新青年茶馆成立时间与理念：2023 年创立于云南，结合茶饮与创意生活方式，致力于解构传统茶文化，重构 “无边界的饮茶生活”，以新青年视角探索云南风物。探索云南风物的过程，我们将以新青年的视角，解构传统茶饮的魅力，重构充满创意与温度的新式茶文化。通过嗅觉、味觉、听觉乃至视觉的世界里，讲述云南的故事"}
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