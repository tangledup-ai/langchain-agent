from dataclasses import dataclass, field
from typing import Type, Callable, List
import tyro
import random

from lang_agent.config import LLMKeyConfig
from lang_agent.pipeline import Pipeline, PipelineConfig

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, ToolMessage

@tyro.conf.configure(tyro.conf.SuppressFixed)
@dataclass
class ValidatorConfig(LLMKeyConfig):
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
            model=self.config.llm_name,
            model_provider=self.config.llm_provider,
            base_url=self.config.base_url,
            api_key=self.config.api_key
        )

    def default_correct(self, inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
        instructions = (
            "Given an actual answer and an expected answer, determine whether"
            " the actual answer contains all of the information in the"
            " expected answer. First provide your reasoning, then respond with"
            " your final judgment.\n\n"
            "Format your response EXACTLY as follows:\n"
            "EXPLANATION: <your reasoning here>\n"
            "JUDGMENT: <CORRECT or INCORRECT>"
        )
        actual_answer = outputs["output"][-1].content
        expected_answer = reference_outputs["answer"]

        if expected_answer is None:
            return {"score": True, "comment": "No expected answer provided, auto-pass."}

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

        response_text = response.content
        
        # Parse the explanation and judgment from the response
        explanation = ""
        is_correct = False
        
        if "EXPLANATION:" in response_text:
            parts = response_text.split("JUDGMENT:")
            explanation = parts[0].replace("EXPLANATION:", "").strip()
            if len(parts) > 1:
                judgment = parts[1].strip().upper()
                is_correct = "CORRECT" in judgment and "INCORRECT" not in judgment
        else:
            # Fallback: check if response contains CORRECT/INCORRECT
            explanation = response_text
            is_correct = "CORRECT" in response_text.upper() and "INCORRECT" not in response_text.upper()

        return {"score": is_correct, "comment": explanation}
    
    def val_tool_use(self, inputs:dict, outputs:dict, reference_outputs:dict)->float:
        tool_uses:List[str] = reference_outputs.get("tool_use")
        if tool_uses is None:
            return 1.0

        tool_msgs = [e for e in outputs["output"] if isinstance(e, ToolMessage)]

        tool_used = []
        for ref_tool in tool_uses:
            st_cond = False
            ref_tool = ref_tool.lower()
            for msg in tool_msgs:
                st_cond = msg.name.lower() in ref_tool
                if st_cond:
                    break
            tool_used.append(st_cond)
        
        return sum(tool_used)/len(tool_uses)

 
    def default_inp_parse(self, inp, pipeline:Pipeline):
        inp = inp["text"]

        if isinstance(inp, str):
            inp = [inp]

        thread_id = str(random.randint(1, 9999999999))
        outs = []
        for usr_inp in inp:
            outs.extend(pipeline.chat(usr_inp, as_raw=True, thread_id=thread_id))

        return outs

    
    def get_val_fnc(self, dataset_name:str)->List[Callable]:
        return self.dict_corr_map.get(dataset_name, [self.default_correct, self.val_tool_use])
    

    def get_inp_fnc(self,dataset_name:str)->Callable:
        # return self.dict_inp_map[dataset_name]
        return self.dict_inp_map.get(dataset_name, self.default_inp_parse)