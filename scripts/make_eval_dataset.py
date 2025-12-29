from langsmith import Client
from loguru import logger


DATASET_NAME = "QA_xiaozhan"

examples = [
    {
        "inputs": {"text": "有没有野星星这杯茶"},
        "outputs": {"answer": "有，野星星（2003年野生大树春茶-生普）采自云南西双版纳原始山林，历经二十余载陈化，汤感醇厚，回甘迅猛，尽显时光韵味。",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "你们这里有没有有密香的茶"},
        "outputs": {"answer": "有，小确幸，小种子，小甜心",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "有果味的茶有哪些?"},
        "outputs": {"answer": "莓烦恼, 放轻松, 花仙子, 悠长假期, 反复喜欢",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "哪些茶有草莓的?"},
        "outputs": {"answer": "花魁soe，醋 | 木瓜莳萝金酒酸",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "想喝点乌龙茶，有什么推荐的吗？"},
        "outputs": {"answer": "少年游，花仙子",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "听说你们这里有创新茶。有酒香味的茶吗？"},
        "outputs": {"answer": "少年游，花仙子",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "听说你们这里有创新茶。有酒香味的茶吗？"},
        "outputs": {"answer": "少年游，花仙子",
                    "tool_use": ["search_dishes"]}
    },
    {
        "inputs": {"text": "有口感甘甜的茶吗?"},
        "outputs": {"answer": "有的，伏身于自然",
                    "tool_use": ["search_dishes"]}
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