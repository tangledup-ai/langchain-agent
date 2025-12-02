from typing import Any, List, Optional, Iterator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks.manager import CallbackManagerForLLMRun


class ReitLLM(BaseChatModel):
    """A simple LLM that repeats the last human message."""

    model_name: str = "reit-llm"

    @property
    def _llm_type(self) -> str:
        """Return the type of LLM."""
        return "reit-llm"

    @property
    def _identifying_params(self) -> dict:
        """Return identifying parameters."""
        return {"model_name": self.model_name}

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate a response by repeating the last human message.

        Args:
            messages: List of messages in the conversation.
            stop: Optional list of stop sequences (not used).
            run_manager: Optional callback manager (not used).
            **kwargs: Additional keyword arguments (not used).

        Returns:
            ChatResult containing the repeated message.
        """
        # Find the last human message
        last_human_message = None
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                last_human_message = message.content
                break

        # If no human message found, return empty string
        if last_human_message is None:
            last_human_message = ""

        # Create the AI message with the repeated content
        ai_message = AIMessage(content=last_human_message)

        # Create and return the ChatResult
        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async version of _generate."""
        return self._generate(messages, stop, run_manager, **kwargs)


# Example usage and test
if __name__ == "__main__":
    # Create the ReitLLM instance
    reit_llm = ReitLLM()

    # Test message
    reit_msg = "the world is beautiful"

    # Create input messages
    inp = [
        SystemMessage(content="REPEAT THE HUMAN MESSAGE AND DO NOTHING ELSE!"),
        HumanMessage(content=reit_msg),
    ]

    # Invoke the LLM
    out = reit_llm.invoke(inp)

    # Print the result
    print(f"Input: '{reit_msg}'")
    print(f"Output: '{out.content}'")
    print(f"Match: {out.content == reit_msg}")

    # Additional test with multiple messages
    print("\n--- Additional Tests ---")

    # Test with multiple human messages (should return the last one)
    inp2 = [
        SystemMessage(content="REPEAT THE HUMAN MESSAGE!"),
        HumanMessage(content="first message"),
        AIMessage(content="some response"),
        HumanMessage(content="second message"),
    ]
    out2 = reit_llm.invoke(inp2)
    print(f"Multiple messages test - Output: '{out2.content}'")

    # Test with no human message
    inp3 = [
        SystemMessage(content="REPEAT THE HUMAN MESSAGE!"),
    ]
    out3 = reit_llm.invoke(inp3)
    print(f"No human message test - Output: '{out3.content}'")
