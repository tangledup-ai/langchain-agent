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
    {
    "inputs": {"text": "你们店里有没有花青素含量高的茶"},
    "outputs": {"answer": "有的，小确幸就是一杯花青素含量高的茶",
    "tool_use": ["search_dishes"]}
    },
    {
    "inputs": {"text": "你们店里面最老的茶是什么茶？"},
    "outputs": {"answer": "我们店里面最老的茶是2003年的野生大树春茶，用来制作野星星",
    "tool_use": ["search_dishes"]}
    },
    {
    "inputs": {"text": "你们店里有没有不含咖啡因的茶？"},
    "outputs": {"answer": "一般不含咖啡因的茶都是花茶，比如玉兰仙仙、拜拜栀子",
    "tool_use": ["search_dishes"]}
    },
    {
    "inputs": {"text": "你们店里面那些茶加入了蜂蜜？"},
    "outputs": {"answer": "我们店里面加入了蜂蜜的茶有：小宇宙",
    "tool_use": ["search_dishes"]}
    },
    {
    "inputs": {"text": "你们店里有什么普洱茶饮品吗？"},
    "outputs": {"answer": "我们店里面的普洱茶饮品有：放轻松、啤啤茶和米 | 无花果叶熟普威士忌米酒酸",
    "tool_use": ["search_dishes"]}
    },
    {
    "inputs": {"text": "我想喝带有蜜香的茶，有推荐吗？"},
    "outputs": {"answer": "我们店里面有很多茶都带有蜜香，这边可以给你推荐比如：小确幸、小种子、伏身于自然、大白白和跳入梦中",
    "tool_use": ["search_dishes"]}
    },
    {
    "inputs": {"text": "有没有带有奶香的茶？"},
    "outputs": {"answer": "有的呢，这边有奶油椰椰和我两最最好，都是带有椰奶香的饮品",
    "tool_use": ["search_dishes"]}
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