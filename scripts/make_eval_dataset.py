from langsmith import Client
from loguru import logger
from dotenv import load_dotenv
import os.path as osp
import os

load_dotenv()

DATASET_NAME = "QA_xiaozhan_sub"
from loguru import logger

ASSETS_DIR = osp.join(osp.dirname(osp.dirname(__file__)), "assets")
if not osp.exists(ASSETS_DIR):
    os.makedirs(ASSETS_DIR)

examples = [
    {
        "inputs": {"text": "请你介绍一下少年右这杯茶"},
        "outputs": {
            "answer": "这是一杯使用武夷肉桂为原料的茶，带有浓郁的肉桂香气和微微的辛辣感，茶汤醇厚，回味悠长，非常适合喜欢浓烈香气的茶友。",
            "tool_use": ["search_dishes"]
        }
    },
    {
    "inputs": {"text": "给我讲讲野心心这杯茶"},
    "outputs": {
      "answer": "野星星选用云南西双版纳野生大树春茶，历经二十多年陈化，茶汤醇厚饱满，回甘迅猛，带着明显的岁月沉香与山野气息。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "介绍一下小甜新"},
    "outputs": {
      "answer": "小甜心来自芒景村古树生普，兰香与蜜韵交织，入口柔和，回甘悠长，是一款耐喝又有层次的老料生普。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "小盏，什么是大白百？"},
    "outputs": {
      "answer": "大白白是一款2012年的老白茶，经过多年陈化，蜜香温润，茶汤醇厚顺滑，回甘绵长，整体风格安静而沉稳。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "帮我介绍下引你进山林"},
    "outputs": {
      "answer": "引你入山林以新会陈皮搭配云南白茶，茶汤清甜柔和，带有淡淡的花果香与陈皮的温润气息，喝起来非常舒服。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "伏身于大自然是什么味道"},
    "outputs": {
      "answer": "伏身于自然将云南滇红与玫瑰慢煮融合，花香馥郁，入口醇厚甘甜，蜜香在口中停留很久，温暖又放松。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "介绍一下小野仔"},
    "outputs": {
      "answer": "小野子选用云南古树晒红制作，蜜香高扬，口感甜润顺滑，回甘明显，是一款非常友好的红茶。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "放轻松这杯喝起来怎么样"},
    "outputs": {
      "answer": "放轻松是小青柑搭配熟普，茶汤醇厚顺滑，柑香清新提亮整体口感，非常适合饭后或想放松的时候。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "啤啤查是酒吗"},
    "outputs": {
      "answer": "啤啤茶是一款无酒精气泡茶，以普洱和玫瑰为茶底，气泡清爽，入口有类似啤酒的畅快感，但完全不含酒精。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "鲜叶康普查有什么特点"},
    "outputs": {
      "answer": "鲜叶康普茶经过自然发酵，带有轻盈气泡和清爽酸甜感，同时富含益生菌，整体低糖低卡，口感非常清新。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "介绍一下寻静密"},
    "outputs": {
      "answer": "寻静谧融合茉莉绿茶与抹茶，茶感温润微涩，搭配栀子花香奶盖与海苔碎，层次细腻，整体风格安静沉稳。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "小陶燃是什么茶"},
    "outputs": {
      "answer": "小陶然是一款熟普黑茶，选用布朗山原料发酵，陈香明显，滋味甜醇饱满，口感厚实顺滑。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "花仙仔适合什么人喝"},
    "outputs": {
      "answer": "花仙子是东方美人乌龙茶，带有天然熟果蜜香，茶感柔和细腻，很适合喜欢花果香型乌龙的茶友。",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "介绍下小美慢"},
    "outputs": {
      "answer": "小美满选用福鼎老寿眉白茶，带有枣香和淡淡药香，口感甘润持久，是一款很有岁月感的白茶。",
    }
  },
  {
    "inputs": {"text": "你叫什么名字"},
    "outputs": {
      "answer": "我叫小盏，是半盏新青年茶馆的智能助手",
    }
  },
  {
    "inputs": {"text": "我今天很开心"},
    "outputs": {
      "answer": "太棒啦！看到你开心，我的茶盖都忍不住轻轻晃起来啦",
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "你好可爱呀！"},
    "outputs": {
      "answer": "谢谢你呀～我的小蓝鼻子都害羞得微微发烫啦！每次被夸可爱",
    }
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