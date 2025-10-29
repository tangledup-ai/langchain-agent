from dataclasses import dataclass, field
from typing import Type, Callable, List
import tyro

from lang_agent.config import KeyConfig
from lang_agent.pipeline import Pipeline, PipelineConfig

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, ToolMessage

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ValidatorConfig(KeyConfig):
    _target: Type = field(default_factory=lambda:Validator)


class Validator:
    def __init__(self, config: ValidatorConfig):
        self.config = config

        self.populate_modules()

        # NOTE: Need to register function here
        self.dict_corr_map = {
            "dev_langagent" : [self.default_correct, self.val_tool_use]
        }

        # NOTE: Need to register function here
        self.dict_inp_map = {
            "dev_langagent" : self.default_inp_parse
        }


    def populate_modules(self):
        self.judge_llm = init_chat_model(
            model="qwen-turbo",
            model_provider="openai",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=self.config.api_key
        )

    # NOTE: for every dataset; need one of these
    def default_correct(self, inputs: dict, outputs: dict, reference_outputs: dict) -> bool:
        instructions = (
            "Given an actual answer and an expected answer, determine whether"
            " the actual answer contains all of the information in the"
            " expected answer. Respond with 'CORRECT' if the actual answer"
            " does contain all of the expected information and 'INCORRECT'"
            " otherwise. Do not include anything else in your response."
        )
        actual_answer = outputs["output"][-1].content
        expected_answer = reference_outputs["answer"]

        user_msg = (
            f"ACTUAL ANSWER: {actual_answer}"
            f"\n\nEXPECTED ANSWER: {expected_answer}"
        )

        response = self.judge_llm.invoke(
            [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_msg}
            ]
        )

        return response.content.upper() == "CORRECT"
    
    def val_tool_use(self, inputs:dict, outputs:dict, reference_outputs:dict)->float:
        tool_uses:List[str] = reference_outputs.get("tool_use")
        if tool_uses is None:
            return 1.0

        tool_msgs = [e for e in outputs["output"] if isinstance(e, ToolMessage)]

        # check if all tools are used
        tool_used = []
        for ref_tool in tool_uses:
            st_cond = False
            ref_tool = ref_tool.lower()
            for msg in tool_msgs:
                st_cond = ref_tool in msg.name.lower()
                if st_cond:
                    break
            tool_used.append(st_cond)
        
        return sum(tool_used)/len(tool_uses)

    

    # NOTE: for every dataset; need one of these
    def default_inp_parse(self, inp, pipeline:Pipeline):
        inp = inp["text"]

        if isinstance(inp, str):
            inp = [inp]

        outs = []
        for usr_inp in inp:
            outs.extend(pipeline.chat(usr_inp, as_raw=True))

        return outs

    
    def get_val_fnc(self, dataset_name:str)->List[Callable]:
        return self.dict_corr_map.get(dataset_name, [self.default_correct, self.val_tool_use])
    

    def get_inp_fnc(self,dataset_name:str)->Callable:
        # return self.dict_inp_map[dataset_name]
        return self.dict_inp_map.get(dataset_name, self.default_inp_parse)