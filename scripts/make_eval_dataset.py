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
        "inputs": {"text": "请你介绍一些下这杯俯身于自然"},
        "outputs": {
            "answer": "伏身于自然是一款充满自然气息的茶饮，选用来自深山的茶叶，带有清新的草木香气和微微的甘甜。茶汤色泽清亮，口感细腻，仿佛与大自然融为一体。",
            "tool_use": ["search_dishes"]
        }
    },
    {
        "inputs": {"text": "请你介绍一下少年右这杯茶"},
        "outputs": {
            "answer": "这是一杯使用武夷肉桂为原料的茶，带有浓郁的肉桂香气和微微的辛辣感，茶汤醇厚，回味悠长，非常适合喜欢浓烈香气的茶友。",
            "tool_use": ["search_dishes"]
        }
    },
    {
        "inputs": {"text": "小盏，介绍一下奶油椰椰这杯茶"},
        "outputs": {
            "answer": "你好呀，我是小盏，让我来给你介绍一下我们的奶油椰椰，它是由新鲜的椰果和浓郁的奶油搭配而成，口感顺滑，带有淡淡的椰香与奶香，犹如初夏的清风，轻盈愉悦。",
            "tool_use": ["search_dishes"]
        }
    },
    {
        "inputs": {"text": "介绍一下这杯小确幸"},
        "outputs": {
            "answer": "好的，我们的小确幸是使用了云南墨红玫瑰花朵与清新的绿茶混合，呈现出花香与茶香交织的独特味道，香气悠长，回味如甜美的小幸福。",
            "tool_use": ["search_dishes"]
        }
    },
    {
        "inputs": {"text": "请你介绍一下这杯我两最最好"},
        "outputs": {
            "answer": "这杯‘我俩最最好’是采用了精选的云南普洱茶和桂花为主料，带有淡淡的花香与普洱的醇厚味道，给人一种温暖的感觉，适合和最好的朋友共享。",
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
      "tool_use": ["search_dishes"]
    }
  },
  {
    "inputs": {"text": "玉兰仙仙是什么风味"},
    "outputs": {
      "answer": "玉兰仙仙以白玉兰和茉莉花窨制，花香高扬纯净，冷萃呈现出清透而优雅的花香口感。",
      "tool_use": ["search_dishes"]
    }
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