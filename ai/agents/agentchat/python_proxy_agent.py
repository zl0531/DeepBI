import asyncio
from collections import defaultdict
import copy
import json
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
from ai.agents import oai
from .agent import Agent
import numpy as np
from sklearn.linear_model import LinearRegression
import ast
import re
from ai.backend.util import base_util
from ai.agents.code_utils import (
    DEFAULT_MODEL,
    UNKNOWN,
    execute_code,
    extract_code,
    infer_lang,
    append_report_logger,
)
import traceback
from ai.backend.util.write_log import logger
from ai.agents.code_utils import tell_logger
from ai.backend.util.base_util import dbinfo_decode
from ai.backend.util import database_util

try:
    from termcolor import colored
except ImportError:
    def colored(x, *args, **kwargs):
        return x


# 函数，用于精确到小数点后两位
def format_decimal(value):
    if isinstance(value, float):
        return round(value, 2)
    elif isinstance(value, int):
        return value
    return value


def calculate_dispersion(data):
    x_values = np.array([point[0] for point in data])
    y_values = np.array([point[1] for point in data])
    x_std, y_std = np.std(x_values), np.std(y_values)
    dispersion = format_decimal((x_std + y_std) / 2)
    correlation = np.corrcoef(x_values, y_values)[0, 1]
    correlation = format_decimal(correlation)
    x_min, x_max = format_decimal(min(x_values)), format_decimal(max(x_values))
    y_min, y_max = format_decimal(min(y_values)), format_decimal(max(y_values))
    ave_x = format_decimal(sum(x_values) / len(x_values))
    ave_y = format_decimal(sum(y_values) / len(y_values))
    return dispersion, correlation, (x_min, x_max), (y_min, y_max), (ave_x, ave_y)


def calculate_trendline(data):
    x_values = np.array([point[0] for point in data]).reshape(-1, 1)
    y_values = np.array([point[1] for point in data])

    model = LinearRegression().fit(x_values, y_values)
    slope = model.coef_[0]
    intercept = model.intercept_

    return slope, intercept


def calculate_distance(point1, point2):
    return np.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)


def count_outliers(data):
    distances = []
    # 计算所有数据点之间的距离
    for i in range(len(data)):
        for j in range(i + 1, len(data)):
            distances.append(calculate_distance(data[i], data[j]))
    # 计算平均距离
    avg_distance = np.mean(distances)
    # 找出中值点
    median_point = np.median(data, axis=0)
    # 计算距离中值点的距离，并检查是否大于平均距离的200%
    outliers_count = sum([1 for point in data if calculate_distance(point, median_point) > avg_distance * 2])
    if outliers_count < 5:
        outliers = [format_decimal(point) for point in data if any(calculate_distance(point, median_point) > avg_distance * 2 for p in data)]
    else:
        outliers = [format_decimal(point) for point in data if any(calculate_distance(point, median_point) > avg_distance * 2 for p in data)]
        outliers.sort(key=lambda point: abs(calculate_distance(point, median_point)), reverse=True)
        outliers = outliers[:5]
    return outliers_count, outliers


class PythonProxyAgent(Agent):
    """(In preview) A class for generic conversable agents which can be configured as assistant or user proxy.

    After receiving each message, the agent will send a reply to the sender unless the msg is a termination msg.
    For example, AssistantAgent and UserProxyAgent are subclasses of this class,
    configured with different default settings.

    To modify auto reply, override `generate_reply` method.
    To disable/enable human response in every turn, set `human_input_mode` to "NEVER" or "ALWAYS".
    To modify the way to get human input, override `get_human_input` method.
    To modify the way to execute code blocks, single code block, or function call, override `execute_code_blocks`,
    `run_code`, and `execute_function` methods respectively.
    To customize the initial message when a conversation starts, override `generate_init_message` method.

    """

    DEFAULT_CONFIG = {
        "model": DEFAULT_MODEL,
    }
    MAX_CONSECUTIVE_AUTO_REPLY = 100  # maximum number of consecutive auto replies (subject to future change)

    def __init__(
        self,
        name: str,
        system_message: Optional[str] = None,
        is_termination_msg: Optional[Callable[[Dict], bool]] = None,
        max_consecutive_auto_reply: Optional[int] = None,
        human_input_mode: Optional[str] = "TERMINATE",
        function_map: Optional[Dict[str, Callable]] = None,
        code_execution_config: Optional[Union[Dict, bool]] = None,
        llm_config: Optional[Union[Dict, bool]] = None,
        default_auto_reply: Optional[Union[str, Dict, None]] = "",
        websocket: Optional = None,
        user_name: Optional[str] = "default_user",
        outgoing: Optional = None,
        incoming: Optional = None,
        db_id: Optional = None,
        is_log_out: Optional[bool] = True,
        report_file_name: Optional[str] = None,
        is_auto_pilot: Optional[bool] = False
    ):
        """
        Args:
            name (str): name of the agent.
            system_message (str): system message for the ChatCompletion inference.
            is_termination_msg (function): a function that takes a message in the form of a dictionary
                and returns a boolean value indicating if this received message is a termination message.
                The dict can contain the following keys: "content", "role", "name", "function_call".
            max_consecutive_auto_reply (int): the maximum number of consecutive auto replies.
                default to None (no limit provided, class attribute MAX_CONSECUTIVE_AUTO_REPLY will be used as the limit in this case).
                When set to 0, no auto reply will be generated.
            human_input_mode (str): whether to ask for human inputs every time a message is received.
                Possible values are "ALWAYS", "TERMINATE", "NEVER".
                (1) When "ALWAYS", the agent prompts for human input every time a message is received.
                    Under this mode, the conversation stops when the human input is "exit",
                    or when is_termination_msg is True and there is no human input.
                (2) When "TERMINATE", the agent only prompts for human input only when a termination message is received or
                    the number of auto reply reaches the max_consecutive_auto_reply.
                (3) When "NEVER", the agent will never prompt for human input. Under this mode, the conversation stops
                    when the number of auto reply reaches the max_consecutive_auto_reply or when is_termination_msg is True.
            function_map (dict[str, callable]): Mapping function names (passed to openai) to callable functions.
            code_execution_config (dict or False): config for the code execution.
                To disable code execution, set to False. Otherwise, set to a dictionary with the following keys:
                - work_dir (Optional, str): The working directory for the code execution.
                    If None, a default working directory will be used.
                    The default working directory is the "extensions" directory under
                    "path_to_autogen".
                - use_docker (Optional, list, str or bool): The docker image to use for code execution.
                    If a list or a str of image name(s) is provided, the code will be executed in a docker container
                    with the first image successfully pulled.
                    If None, False or empty, the code will be executed in the current environment.
                    Default is True when the docker python package is installed.
                    When set to True, a default list will be used.
                    We strongly recommend using docker for code execution.
                - timeout (Optional, int): The maximum execution time in seconds.
                - last_n_messages (Experimental, Optional, int): The number of messages to look back for code execution. Default to 1.
            llm_config (dict or False): llm inference configuration.
                Please refer to [Completion.create](/docs/reference/oai/completion#create)
                for available options.
                To disable llm-based auto reply, set to False.
            default_auto_reply (str or dict or None): default auto reply when no code execution or llm-based reply is generated.
        -------------------------------------------------------------------------------------------
        """
        super().__init__(name)
        # a dictionary of conversations, default value is list
        self.delay_messages = None
        self._oai_messages = defaultdict(list)
        self._oai_system_message = [{"content": system_message, "role": "system"}]
        self._is_termination_msg = (
            is_termination_msg if is_termination_msg is not None else (lambda x: x.get("content") == "TERMINATE")
        )
        if llm_config is False:
            self.llm_config = False
        else:
            self.llm_config = self.DEFAULT_CONFIG.copy()
            if isinstance(llm_config, dict):
                self.llm_config.update(llm_config)

        self._code_execution_config = {} if code_execution_config is None else code_execution_config
        self.human_input_mode = human_input_mode
        self._max_consecutive_auto_reply = (
            max_consecutive_auto_reply if max_consecutive_auto_reply is not None else self.MAX_CONSECUTIVE_AUTO_REPLY
        )
        self._consecutive_auto_reply_counter = defaultdict(int)
        self._max_consecutive_auto_reply_dict = defaultdict(self.max_consecutive_auto_reply)
        self._function_map = {} if function_map is None else function_map
        self._default_auto_reply = default_auto_reply
        self._reply_func_list = []
        self.reply_at_receive = defaultdict(bool)
        # self.register_reply([Agent, None], PythonProxyAgent.generate_oai_reply)
        self.register_reply([Agent, None], PythonProxyAgent.generate_function_call_reply)
        # self.register_reply([Agent, None], HumanProxyAgent.check_termination_and_human_reply)
        self.register_reply([Agent, None], PythonProxyAgent.generate_code_execution_reply)

        self.websocket = websocket
        self.user_name = user_name
        self.outgoing = outgoing
        self.incoming = incoming
        self.db_id = db_id
        self.is_log_out = is_log_out
        self.report_file_name = report_file_name
        self.is_auto_pilot = is_auto_pilot
        delay_messages = self.delay_messages

    def register_reply(
        self,
        trigger: Union[Type[Agent], str, Agent, Callable[[Agent], bool], List],
        reply_func: Callable,
        position: Optional[int] = 0,
        config: Optional[Any] = None,
        reset_config: Optional[Callable] = None,
    ):
        """Register a reply function.

        The reply function will be called when the trigger matches the sender.
        The function registered later will be checked earlier by default.
        To change the order, set the position to a positive integer.

        Args:
            trigger (Agent class, str, Agent instance, callable, or list): the trigger.
                - If a class is provided, the reply function will be called when the sender is an instance of the class.
                - If a string is provided, the reply function will be called when the sender's name matches the string.
                - If an agent instance is provided, the reply function will be called when the sender is the agent instance.
                - If a callable is provided, the reply function will be called when the callable returns True.
                - If a list is provided, the reply function will be called when any of the triggers in the list is activated.
                - If None is provided, the reply function will be called only when the sender is None.
                Note: Be sure to register `None` as a trigger if you would like to trigger an auto-reply function with non-empty messages and `sender=None`.
            reply_func (Callable): the reply function.
                The function takes a recipient agent, a list of messages, a sender agent and a config as input and returns a reply message.
        ```python
        def reply_func(
            recipient: ConversableAgent,
            messages: Optional[List[Dict]] = None,
            sender: Optional[Agent] = None,
            config: Optional[Any] = None,
        ) -> Union[str, Dict, None]:
        ```
            position (int): the position of the reply function in the reply function list.
                The function registered later will be checked earlier by default.
                To change the order, set the position to a positive integer.
            config (Any): the config to be passed to the reply function.
                When an agent is reset, the config will be reset to the original value.
            reset_config (Callable): the function to reset the config.
                The function returns None. Signature: ```def reset_config(config: Any)```

        --------------------------------------------------------------------------------------------
        """
        if not isinstance(trigger, (type, str, Agent, Callable, list)):
            raise ValueError("trigger must be a class, a string, an agent, a callable or a list.")
        self._reply_func_list.insert(
            position,
            {
                "trigger": trigger,
                "reply_func": reply_func,
                "config": copy.copy(config),
                "init_config": config,
                "reset_config": reset_config,
            },
        )

    @property
    def system_message(self):
        """Return the system message."""
        return self._oai_system_message[0]["content"]

    def update_system_message(self, system_message: str):
        """Update the system message.

        Args:
            system_message (str): system message for the ChatCompletion inference.
        """
        self._oai_system_message[0]["content"] = system_message

    def update_max_consecutive_auto_reply(self, value: int, sender: Optional[Agent] = None):
        """Update the maximum number of consecutive auto replies.

        Args:
            value (int): the maximum number of consecutive auto replies.
            sender (Agent): when the sender is provided, only update the max_consecutive_auto_reply for that sender.
        """
        if sender is None:
            self._max_consecutive_auto_reply = value
            for k in self._max_consecutive_auto_reply_dict:
                self._max_consecutive_auto_reply_dict[k] = value
        else:
            self._max_consecutive_auto_reply_dict[sender] = value

    def max_consecutive_auto_reply(self, sender: Optional[Agent] = None) -> int:
        """The maximum number of consecutive auto replies."""
        return self._max_consecutive_auto_reply if sender is None else self._max_consecutive_auto_reply_dict[sender]

    @property
    def chat_messages(self) -> Dict[Agent, List[Dict]]:
        """A dictionary of conversations from agent to list of messages."""
        return self._oai_messages

    def last_message(self, agent: Optional[Agent] = None) -> Dict:
        """The last message exchanged with the agent.

        Args:
            agent (Agent): The agent in the conversation.
                If None and more than one agent's conversations are found, an error will be raised.
                If None and only one conversation is found, the last message of the only conversation will be returned.

        Returns:
            The last message exchanged with the agent.
        --------------------------------------------------------------------------------
        """
        if agent is None:
            n_conversations = len(self._oai_messages)
            if n_conversations == 0:
                return None
            if n_conversations == 1:
                for conversation in self._oai_messages.values():
                    return conversation[-1]
            raise ValueError("More than one conversation is found. Please specify the sender to get the last message.")
        return self._oai_messages[agent][-1]

    @property
    def use_docker(self) -> Union[bool, str, None]:
        """Bool value of whether to use docker to execute the code,
        or str value of the docker image name to use, or None when code execution is disabled.
        """
        return None if self._code_execution_config is False else self._code_execution_config.get("use_docker")

    @staticmethod
    def _message_to_dict(message: Union[Dict, str]):
        """Convert a message to a dictionary.

        The message can be a string or a dictionary. The string will be put in the "content" field of the new dictionary.
        """
        if isinstance(message, str):
            return {"content": message}
        else:
            return message

    def _append_oai_message(self, message: Union[Dict, str], role, conversation_id: Agent) -> bool:
        """Append a message to the ChatCompletion conversation.

        If the message received is a string, it will be put in the "content" field of the new dictionary.
        If the message received is a dictionary but does not have any of the two fields "content" or "function_call",
            this message is not a valid ChatCompletion message.
        If only "function_call" is provided, "content" will be set to None if not provided, and the role of the message will be forced "assistant".

        Args:
            message (dict or str): message to be appended to the ChatCompletion conversation.
            role (str): role of the message, can be "assistant" or "function".
            conversation_id (Agent): id of the conversation, should be the recipient or sender.

        Returns:
            bool: whether the message is appended to the ChatCompletion conversation.

        -------------------------------------------------------------------------------
        """
        message = self._message_to_dict(message)
        # create oai message to be appended to the oai conversation that can be passed to oai directly.
        oai_message = {k: message[k] for k in ("content", "function_call", "name", "context") if k in message}
        if "content" not in oai_message:
            if "function_call" in oai_message:
                oai_message["content"] = None  # if only function_call is provided, content will be set to None.
            else:
                return False

        oai_message["role"] = "function" if message.get("role") == "function" else role
        if "function_call" in oai_message:
            oai_message["role"] = "assistant"  # only messages with role 'assistant' can have a function call.
        self._oai_messages[conversation_id].append(oai_message)
        return True

    async def send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ) -> bool:
        """Send a message to another agent.

        Args:
            message (dict or str): message to be sent.
                The message could contain the following fields:
                - content (str): Required, the content of the message. (Can be None)
                - function_call (str): the name of the function to be called.
                - name (str): the name of the function to be called.
                - role (str): the role of the message, any role that is not "function"
                    will be modified to "assistant".
                - context (dict): the context of the message, which will be passed to
                    [Completion.create](../oai/Completion#create).
                    For example, one agent can send a message A as:
        ```python
        {
            "content": lambda context: context["use_tool_msg"],
            "context": {
                "use_tool_msg": "Use tool X if they are relevant."
            }
        }
        ```
                    Next time, one agent can send a message B with a different "use_tool_msg".
                    Then the content of message A will be refreshed to the new "use_tool_msg".
                    So effectively, this provides a way for an agent to send a "link" and modify
                    the content of the "link" later.
            recipient (Agent): the recipient of the message.
            request_reply (bool or None): whether to request a reply from the recipient.
            silent (bool or None): (Experimental) whether to print the message sent.

        Raises:
            ValueError: if the message can't be converted into a valid ChatCompletion message.
        """
        # When the agent composes and sends the message, the role of the message is "assistant"
        # unless it's "function".

        valid = self._append_oai_message(message, "assistant", recipient)
        if valid:
            await recipient.receive(message, self, request_reply, silent)
        else:

            raise ValueError(
                "Message can't be converted into a valid ChatCompletion message. Either content or function_call must be provided."
            )

    async def a_send(
        self,
        message: Union[Dict, str],
        recipient: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ) -> bool:
        """(async) Send a message to another agent.

        Args:
            message (dict or str): message to be sent.
                The message could contain the following fields:
                - content (str): Required, the content of the message. (Can be None)
                - function_call (str): the name of the function to be called.
                - name (str): the name of the function to be called.
                - role (str): the role of the message, any role that is not "function"
                    will be modified to "assistant".
                - context (dict): the context of the message, which will be passed to
                    [Completion.create](../oai/Completion#create).
                    For example, one agent can send a message A as:
        ```python
        {
            "content": lambda context: context["use_tool_msg"],
            "context": {
                "use_tool_msg": "Use tool X if they are relevant."
            }
        }
        ```
                    Next time, one agent can send a message B with a different "use_tool_msg".
                    Then the content of message A will be refreshed to the new "use_tool_msg".
                    So effectively, this provides a way for an agent to send a "link" and modify
                    the content of the "link" later.
            recipient (Agent): the recipient of the message.
            request_reply (bool or None): whether to request a reply from the recipient.
            silent (bool or None): (Experimental) whether to print the message sent.

        Raises:
            ValueError: if the message can't be converted into a valid ChatCompletion message.
        """
        # When the agent composes and sends the message, the role of the message is "assistant"
        # unless it's "function".
        valid = self._append_oai_message(message, "assistant", recipient)
        if valid:
            await recipient.a_receive(message, self, request_reply, silent)
        else:
            raise ValueError(
                "Message can't be converted into a valid ChatCompletion message. Either content or function_call must be provided."
            )

    async def _print_received_message(self, message: Union[Dict, str], sender: Agent):
        # print the message received
        print(colored(sender.name, "yellow"), "(to", f"{self.name}):\n", flush=True)

        log_str = str(sender.name) + "(to " + self.name + "): \n"

        if message.get("role") == "function":
            func_print = f"***** Response from calling function \"{message['name']}\" *****"
            print(colored(func_print, "green"), flush=True)
            print(message["content"], flush=True)
            print(colored("*" * len(func_print), "green"), flush=True)

            log_str = log_str + '\n' + str(func_print) + '\n' + str(message["content"]) + '\n' + str(
                "*" * len(func_print))
        else:
            content = message.get("content")
            if content is not None:
                if "context" in message:
                    content = oai.ChatCompletion.instantiate(
                        content,
                        message["context"],
                        self.llm_config and self.llm_config.get("allow_format_str_template", False),
                    )
                print(content, flush=True)

                log_str = log_str + '\n' + str(content)

            if "function_call" in message:
                func_print = f"***** Suggested function Call: {message['function_call'].get('name', '(No function name found)')} *****"
                print(colored(func_print, "green"), flush=True)
                print(
                    "Arguments: \n",
                    message["function_call"].get("arguments", "(No arguments found)"),
                    flush=True,
                    sep="",
                )
                print(colored("*" * len(func_print), "green"), flush=True)

                log_str = log_str + '\n' + str(func_print) + '\n' + "Arguments: \n" + str(
                    message["function_call"].get("arguments", "(No arguments found)")) + '\n' + str(
                    "*" * len(func_print))

        print("\n", "-" * 80, flush=True, sep="")

        log_str = log_str + '\n' + "-" * 80
        if self.is_log_out:
            await tell_logger(self.websocket, log_str)
            append_report_logger(self.report_file_name, log_str)

    async def _process_received_message(self, message, sender, silent):
        message = self._message_to_dict(message)
        # When the agent receives a message, the role of the message is "user". (If 'role' exists and is 'function', it will remain unchanged.)

        valid = self._append_oai_message(message, "user", sender)
        if not valid:
            raise ValueError(
                "Received message can't be converted into a valid ChatCompletion message. Either content or function_call must be provided."
            )
        if not silent:
            await self._print_received_message(message, sender)

    async def receive(
        self,
        message: Union[Dict, str],
        sender: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        """Receive a message from another agent.

        Once a message is received, this function sends a reply to the sender or stop.
        The reply can be generated automatically or entered manually by a human.

        Args:
            message (dict or str): message from the sender. If the type is dict, it may contain the following reserved fields (either content or function_call need to be provided).
                1. "content": content of the message, can be None.
                2. "function_call": a dictionary containing the function name and arguments.
                3. "role": role of the message, can be "assistant", "user", "function".
                    This field is only needed to distinguish between "function" or "assistant"/"user".
                4. "name": In most cases, this field is not needed. When the role is "function", this field is needed to indicate the function name.
                5. "context" (dict): the context of the message, which will be passed to
                    [Completion.create](../oai/Completion#create).
            sender: sender of an Agent instance.
            request_reply (bool or None): whether a reply is requested from the sender.
                If None, the value is determined by `self.reply_at_receive[sender]`.
            silent (bool or None): (Experimental) whether to print the message received.

        Raises:
            ValueError: if the message can't be converted into a valid ChatCompletion message.

        ----------------------------------------------------------------------------------------
        """

        await self._process_received_message(message, sender, silent)
        if request_reply is False or request_reply is None and self.reply_at_receive[sender] is False:
            return
        reply = await self.generate_reply(messages=self.chat_messages[sender], sender=sender)
        if reply is not None:
            await self.send(reply, sender, silent=silent)

    async def a_receive(
        self,
        message: Union[Dict, str],
        sender: Agent,
        request_reply: Optional[bool] = None,
        silent: Optional[bool] = False,
    ):
        """(async) Receive a message from another agent.

        Once a message is received, this function sends a reply to the sender or stop.
        The reply can be generated automatically or entered manually by a human.

        Args:
            message (dict or str): message from the sender. If the type is dict, it may contain the following reserved fields (either content or function_call need to be provided).
                1. "content": content of the message, can be None.
                2. "function_call": a dictionary containing the function name and arguments.
                3. "role": role of the message, can be "assistant", "user", "function".
                    This field is only needed to distinguish between "function" or "assistant"/"user".
                4. "name": In most cases, this field is not needed. When the role is "function", this field is needed to indicate the function name.
                5. "context" (dict): the context of the message, which will be passed to
                    [Completion.create](../oai/Completion#create).
            sender: sender of an Agent instance.
            request_reply (bool or None): whether a reply is requested from the sender.
                If None, the value is determined by `self.reply_at_receive[sender]`.
            silent (bool or None): (Experimental) whether to print the message received.

        Raises:
            ValueError: if the message can't be converted into a valid ChatCompletion message.
        """
        await self._process_received_message(message, sender, silent)
        if request_reply is False or request_reply is None and self.reply_at_receive[sender] is False:
            return
        reply = await self.a_generate_reply(sender=sender)
        if reply is not None:
            await self.a_send(reply, sender, silent=silent)

    def _prepare_chat(self, recipient, clear_history):
        self.reset_consecutive_auto_reply_counter(recipient)
        recipient.reset_consecutive_auto_reply_counter(self)
        self.reply_at_receive[recipient] = recipient.reply_at_receive[self] = True
        if clear_history:
            self.clear_history(recipient)
            recipient.clear_history(self)

    async def initiate_chat(
        self,
        recipient: "ConversableAgent",
        clear_history: Optional[bool] = True,
        silent: Optional[bool] = False,
        **context,
    ):
        """Initiate a chat with the recipient agent.

        Reset the consecutive auto reply counter.
        If `clear_history` is True, the chat history with the recipient agent will be cleared.
        `generate_init_message` is called to generate the initial message for the agent.

        Args:
            recipient: the recipient agent.
            clear_history (bool): whether to clear the chat history with the agent.
            silent (bool or None): (Experimental) whether to print the messages for this conversation.
            **context: any context information.
                "message" needs to be provided if the `generate_init_message` method is not overridden.
        """
        self._prepare_chat(recipient, clear_history)
        await self.send(self.generate_init_message(**context), recipient, silent=silent)

    async def a_initiate_chat(
        self,
        recipient: "ConversableAgent",
        clear_history: Optional[bool] = True,
        silent: Optional[bool] = False,
        **context,
    ):
        """(async) Initiate a chat with the recipient agent.

        Reset the consecutive auto reply counter.
        If `clear_history` is True, the chat history with the recipient agent will be cleared.
        `generate_init_message` is called to generate the initial message for the agent.

        Args:
            recipient: the recipient agent.
            clear_history (bool): whether to clear the chat history with the agent.
            silent (bool or None): (Experimental) whether to print the messages for this conversation.
            **context: any context information.
                "message" needs to be provided if the `generate_init_message` method is not overridden.
        """
        self._prepare_chat(recipient, clear_history)
        await self.a_send(self.generate_init_message(**context), recipient, silent=silent)

    def reset(self):
        """Reset the agent.
        """
        self.clear_history()
        self.reset_consecutive_auto_reply_counter()
        self.stop_reply_at_receive()
        for reply_func_tuple in self._reply_func_list:
            if reply_func_tuple["reset_config"] is not None:
                reply_func_tuple["reset_config"](reply_func_tuple["config"])
            else:
                reply_func_tuple["config"] = copy.copy(reply_func_tuple["init_config"])

    def stop_reply_at_receive(self, sender: Optional[Agent] = None):
        """Reset the reply_at_receive of the sender."""
        if sender is None:
            self.reply_at_receive.clear()
        else:
            self.reply_at_receive[sender] = False

    def reset_consecutive_auto_reply_counter(self, sender: Optional[Agent] = None):
        """Reset the consecutive_auto_reply_counter of the sender."""
        if sender is None:
            self._consecutive_auto_reply_counter.clear()
        else:
            self._consecutive_auto_reply_counter[sender] = 0

    def clear_history(self, agent: Optional[Agent] = None):
        """Clear the chat history of the agent.

        Args:
            agent: the agent with whom the chat history to clear. If None, clear the chat history with all agents.
        """
        if agent is None:
            self._oai_messages.clear()
        else:
            self._oai_messages[agent].clear()

    def generate_oai_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        config: Optional[Any] = None,
    ) -> Tuple[bool, Union[str, Dict, None]]:
        """Generate a reply using autogen.oai.
        """
        llm_config = self.llm_config if config is None else config
        if llm_config is False:
            return False, None
        if messages is None:
            messages = self._oai_messages[sender]

        # TODO: #1143 handle token limit exceeded error
        response = oai.ChatCompletion.create(
            context=messages[-1].pop("context", None),
            messages=self._oai_system_message + messages,
            agent_name=self.name,
            **llm_config
        )

        return True, oai.ChatCompletion.extract_text_or_function_call(response)[0]

    async def generate_code_execution_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        config: Optional[Any] = None,

    ):
        """Generate a reply using code execution.
        """
        from ai.agents.agent_instance_util import AgentInstanceUtil
        code_execution_config = config if config is not None else self._code_execution_config
        # print('self._code_execution_config :', self._code_execution_config)

        if code_execution_config is False:
            return False, None
        if messages is None:
            messages = self._oai_messages[sender]
        last_n_messages = code_execution_config.pop("last_n_messages", 1)
        base_content = []

        # iterate through the last n messages reversly
        # if code blocks are found, execute the code blocks and return the output
        # if no code blocks are found, continue
        for i in range(min(len(messages), last_n_messages)):
            message = messages[-(i + 1)]
            # print(self.name, ' , [generate_code_execution_reply.message] : ', message)
            if message["content"] is None:
                continue
            code_blocks = extract_code(message["content"])
            if len(code_blocks) == 1 and code_blocks[0][0] == UNKNOWN:
                continue

            if len(code_blocks) == 1 and code_blocks[0][0] != 'python':
                # continue
                if self.is_auto_pilot:
                    # if is auto pilot, no code TERMINATE
                    return True, "执行失败，请提供可执行的Python代码。"
                else:
                    return True, f"exitcode:exitcode failed\nCode output: Please give me executable python code.\n"
            if self.db_id is not None and int(self.db_id) > 0:
                obj = database_util.Main(self.db_id)
                if_suss, db_info = obj.run_decode()
                if if_suss:
                    code_blocks = [(item[0], dbinfo_decode(item[1], db_info)) if isinstance(item[1], str) else item for
                                   item in
                                   code_blocks]

                    # code_blocks = self.replace_ab_with_ac(code_blocks, db_info)
                    # print('new_code_blocks : ', code_blocks)

            # found code blocks, execute code and push "last_n_messages" back
            exitcode, logs = self.execute_code_blocks(code_blocks)
            code_execution_config["last_n_messages"] = last_n_messages
            exitcode2str = "execution succeeded" if exitcode == 0 else "execution failed"
            length = 10000
            if not str(logs).__contains__('echart_name'):
                if "html" in logs or "HTML" in logs:
                    return True, f"exitcode:exitcode failed\nCode output:Please do not output html files. The front end cannot display them. Please generate the correct echarts code."
                if len(logs) > length:
                    print(' ++++++++++ Length exceeds 10000 characters limit, cropped  +++++++++++++++++')
                    logs = logs[:length]
                return True, f"exitcode: {exitcode} ({exitcode2str})\nCode output: {logs}"
            else:
                try:
                    if "'echart_name'" in str(logs):
                        logs = json.dumps(eval(str(logs)))
                    logs = json.loads(str(logs))
                except Exception as e:
                    return True, f"exitcode:exitcode failed\nCode output: There is an error in the JSON code causing parsing errors,Please modify the JSON code for me:{traceback.format_exc()}"
                for index, entry in enumerate(logs):
                    if 'echart_name' in entry and 'echart_code' in entry:
                        if isinstance(entry['echart_code'], str):
                            entry['echart_code'] = json.loads(entry['entry']['echart_code'])
                        if "series" in entry['echart_code']:
                            series_data = entry['echart_code']['series']
                            formatted_series_list = []
                            for series_data in series_data:
                                if series_data['type'] in ["bar", "line"]:
                                    formatted_series_data = [format_decimal(value) for value in series_data['data']]
                                elif series_data['type'] in ["pie", "gauge", "funnel"]:
                                    formatted_series_data = [{"name": d["name"], "value": format_decimal(d["value"])} for d in series_data['data']]
                                elif series_data['type'] in ['graph']:
                                    formatted_series_data = [
                                        {'name': data_point['name'], 'symbolSize': format_decimal(data_point['symbolSize'])}
                                        for data_point in series_data['data']]
                                elif series_data['type'] in ["Kline", "radar", "heatmap", "scatter", "themeRiver", 'parallel', 'effectScatter']:
                                    formatted_series_data = [[format_decimal(value) for value in sublist] for sublist in
                                                             series_data['data']]
                                else:
                                    formatted_series_data = series_data['data']
                                series_data['data'] = formatted_series_data
                                formatted_series_list.append(series_data)
                            entry['echart_code']['series'] = formatted_series_list
                        base_content.append(entry)
                    # this is autopilot
                    if self.is_auto_pilot:
                        # if have multy echarts
                        if index != len(logs) - 1:
                            continue
                        return True, f"exitcode: {exitcode} ({exitcode2str})\nCode output: 图像已生成,任务执行成功！图表数据：{base_content}"

                    # not autopilot
                    if not self.is_auto_pilot:
                        agent_instance_util = AgentInstanceUtil(user_name=str(self.user_name),
                                                                delay_messages=self.delay_messages,
                                                                outgoing=self.outgoing,
                                                                incoming=self.incoming,
                                                                websocket=self.websocket
                                                                )
                        bi_proxy = agent_instance_util.get_agent_bi_proxy()
                        # Call the interface to generate pictures
                        for img_str in base_content:
                            echart_name = img_str.get('echart_name')
                            echart_code = img_str.get('echart_code')

                            if len(echart_code) > 0 and str(echart_code).__contains__('x'):
                                print("echart_name : ", echart_name)
                                await bi_proxy.run_echart_code(str(echart_code), echart_name)
                    # 初始化一个空列表来保存每个echart的信息
                    echarts_data, series_data = [], []
                    xAxis_data_tag = 0
                    # 遍历echarts_code列表，提取数据并构造字典
                    for echart in base_content:
                        echart_name = echart['echart_name']
                        for serie in echart['echart_code']['series']:
                            try:
                                seri_info = {
                                    'type': serie['type'],
                                    'name': serie['name'],
                                    'data': serie['data']
                                }
                            except Exception as e:
                                seri_info = {
                                    'type': serie['type'],
                                    'data': serie['data']
                                }
                            series_data.append(seri_info)
                            if "xAxis" in echart["echart_code"]:
                                xAxis_data = echart['echart_code']['xAxis'][0]['data']
                                xAxis_data_tag = 1
                                if "%Y-%m" in xAxis_data:
                                    return True, f"exitcode:exitcode failed\nCode output:The SQL code query is incorrect. The query date should be %, not %%. Just for example: SELECT DATE_FORMAT(event_time, '%Y-%m-%d') is correct, but SELECT DATE_FORMAT(event_time, '%%Y -%%m-%%d') is wrong!"
                    if xAxis_data_tag and not self.is_auto_pilot:

                        echart_dict = {
                            'echart_name': echart_name,
                            'series': series_data,
                            'xAxis_data': xAxis_data
                        }
                        if echart_dict['series'][0]['type'] == 'scatter':
                            if (len(echart_dict['series']) == 1):
                                data = echart_dict['series'][0]['data']
                                if (len(data) < 10):
                                    return True, f"exitcode: {exitcode} ({exitcode2str})\nCode output: 图像已生成,任务执行成功！请直接分析图表数据：{echart_dict}"
                                data_set, count_tag = set(), 0
                                for i in data:
                                    data_set.add(i[1])
                                    if (len(data_set) == 4):
                                        count_tag = 1
                                        break
                                if (count_tag == 0):
                                    data_dict = {item: 0 for item in data_set}
                                    for i in data:
                                        data_dict[i[1]] += 1
                                    return True, f"exitcode: {exitcode} ({exitcode2str})\ncode output:图像已生成,生成的是散点图,该图的标题为:{echart_dict['echart_name']},描述了其相应的关系." \
                                        f"它的数据一共有{len(data)}个,但是它的取值集合个数较少，每一种取值对应的数量关系为{data_dict}"
                                correlation, dispersion, (x_min, x_max), (y_min, y_max), (
                                    ave_x, ave_y) = calculate_dispersion(data)
                                outliers_count, outliers = count_outliers(data)
                                threshold = 0.6  # 相关性阈值
                                if correlation >= threshold:
                                    slope, intercept = calculate_trendline(data)
                                    return True, f"exitcode: {exitcode} ({exitcode2str})\nCode output:图像已生成,生成的是散点图,该图的标题为:{echart_dict['echart_name']},描述了其相应的关系.如下是它的评价指标:\n离散程度为(标准差）:{correlation},相关性评价指标为{dispersion}" \
                                        f"散点图的x区间范围从{(x_min, x_max)},y区间范围从{(y_min, y_max)},中值点为{(ave_x, ave_y)}。定义一个数据点到中值点的距离大于其所有点至中值点平均距离的2倍作为离群点,则离群点的个数为{outliers_count},其中,最大的是几个离群点为{outliers}" \
                                        "其相关性达到预设的阈值,计算得到其趋势线方程为: y = {:.2f}x+{:.2f}。(注意：这里所有的计算数据都约束到了两位有效小数)".format(slope, intercept)
                                else:
                                    return True, f"Code output:图像已生成,生成的是散点图,该图的标题为:{echart_dict['echart_name']},描述了其相应的关系.如下是它的评价指标:\n离散程度为(标准差）:{correlation},相关性评价指标为{dispersion}" \
                                        f"散点图的x区间范围从{(x_min, x_max)},y区间范围从{(y_min, y_max)},中值点为{(ave_x, ave_y)}。定义一个数据点到中值点的距离大于其所有点至中值点平均距离的2倍作为离群点,则离群点的个数为{outliers_count},其中,最大的是几个离群点为{outliers}" \
                                        f"但由于数据的相关性未达到阈值，即该散点图数据并没有明显的线性关系，无法计算趋势线。(注意：这里所有的计算数据都约束到了两位有效小数)"
                            else:
                                message = f"exitcode: {exitcode} ({exitcode2str})\nCode output:图像已生成,生成的是散点图,该图的标题为:{echart_dict['echart_name']},描述了其相应的关系,一共有{len(echart_dict['series'])}类散点数据:\n"
                                count_class = 0
                                for echart_data in echart_dict['series']:
                                    count_class += 1
                                    data = echart_data['data']
                                    if (len(data) < 10):
                                        message_data = f"第{count_class}类数据为{data}"
                                        message += message_data
                                        continue
                                    else:
                                        data_set, count_tag = set(), 0
                                        for i in data:
                                            data_set.add(i[1])
                                            if (len(data_set) == 4):
                                                count_tag = 1
                                                break
                                        if (count_tag == 0):
                                            data_dict = {item: 0 for item in data_set}
                                            for i in data:
                                                data_dict[i[1]] += 1
                                            message_data = f"名为{echart_data['name']}的数据一共有{len(data)}个,但是它的取值集合个数较少，每一种取值对应的数量关系为{data_dict}"
                                            message += message_data
                                            continue
                                        else:
                                            correlation, dispersion, (x_min, x_max), (y_min, y_max), (
                                                ave_x, ave_y) = calculate_dispersion(data)
                                            outliers_count, outliers = count_outliers(data)
                                            threshold = 0.6  # 相关性阈值
                                            if abs(dispersion) >= threshold:
                                                slope, intercept = calculate_trendline(data)
                                                message_data = f"名为{echart_data['name']}的数据，数据的离散程度为(标准差）:{correlation},相关性评价指标为{dispersion}" \
                                                               f"散点图的x区间范围从{(x_min, x_max)},y区间范围从{(y_min, y_max)},中值点为{(ave_x, ave_y)}。定义一个数据点到中值点的距离大于其所有点至中值点平均距离的2倍作为离群点,则离群点的个数为{outliers_count},其中,最大的是几个离群点为{outliers}" \
                                                               "其相关性达到预设的阈值,计算得到其趋势线方程为: y = {:.2f}x+{:.2f}。\n".format(
                                                                   slope, intercept)
                                                message += message_data
                                                continue
                                            else:
                                                message_data = f"名为{echart_data['name']}的数据,数据的离散程度为(标准差）:{correlation},相关性评价指标为{dispersion}" \
                                                               f"散点图的x区间范围从{(x_min, x_max)},y区间范围从{(y_min, y_max)},中值点为{(ave_x, ave_y)}。离群点的个数为{outliers_count},其中,最大的是几个离群点为{outliers}" \
                                                               f"但由于数据的相关性未达到阈值，即该散点图数据并没有明显的线性关系，无法计算趋势线。\n"
                                                message += message_data
                                                continue
                                message = message + "请对每一类的数据性质都进行详细的分析"
                                return True, f"exitcode: {exitcode} ({exitcode2str})\n{message}"
                    else:
                        echart_dict = {
                            'echart_name': echart_name,
                            'series': series_data,
                        }
                    count_max = 1000
                    echart_dict['series'][0]['data'] = echart_dict['series'][0]['data'][:count_max]
                    if (xAxis_data_tag):
                        echart_dict['xAxis_data'] = echart_dict['xAxis_data'][:count_max]

                    echarts_data.append(echart_dict)
                    if (len(echart_dict['series'][0]['data']) > 999):
                        return True, f"exitcode: {exitcode} ({exitcode2str})\nCode output: 图像已生成,任务执行成功！但由于数据量过大，仅截取了1000条，请直接分析图表这些数据：{echarts_data}"
                    else:
                        return True, f"exitcode: {exitcode} ({exitcode2str})\nCode output: 图像已生成,任务执行成功！请直接分析图表数据：{echarts_data}"
        code_execution_config["last_n_messages"] = last_n_messages

        return False, None

    async def generate_function_call_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        config: Optional[Any] = None,
    ):
        """Generate a reply using function call.
        """

        if config is None:
            config = self
        if messages is None:
            messages = self._oai_messages[sender]
        message = messages[-1]
        if "function_call" in message:
            _, func_return = await self.execute_function(message["function_call"])
            return True, func_return
        return False, None

    async def check_termination_and_human_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        config: Optional[Any] = None,
    ) -> Tuple[bool, Union[str, Dict, None]]:
        """Check if the conversation should be terminated, and if human reply is provided.
        """

        if config is None:
            config = self
        if messages is None:
            messages = self._oai_messages[sender]
        message = messages[-1]
        reply = ""
        no_human_input_msg = ""
        if self.human_input_mode == "ALWAYS":
            # reply = self.get_human_input(
            #     f"Provide feedback to {sender.name}. Press enter to skip and use auto-reply, or type 'exit' to end the conversation: "
            # )
            reply = await self.ask_user(message['content'])
            no_human_input_msg = "NO HUMAN INPUT RECEIVED." if not reply else ""
            # if the human input is empty, and the message is a termination message, then we will terminate the conversation
            reply = reply if reply or not self._is_termination_msg(message) else "exit"
        else:
            if self._consecutive_auto_reply_counter[sender] >= self._max_consecutive_auto_reply_dict[sender]:
                if self.human_input_mode == "NEVER":
                    reply = "exit"
                else:
                    # self.human_input_mode == "TERMINATE":
                    terminate = self._is_termination_msg(message)
                    reply = self.get_human_input(
                        f"Please give feedback to {sender.name}. Press enter or type 'exit' to stop the conversation: "
                        if terminate
                        else f"Please give feedback to {sender.name}. Press enter to skip and use auto-reply, or type 'exit' to stop the conversation: "
                    )
                    no_human_input_msg = "NO HUMAN INPUT RECEIVED." if not reply else ""
                    # if the human input is empty, and the message is a termination message, then we will terminate the conversation
                    reply = reply if reply or not terminate else "exit"
            elif self._is_termination_msg(message):
                if self.human_input_mode == "NEVER":
                    reply = "exit"
                else:
                    # self.human_input_mode == "TERMINATE":
                    reply = self.get_human_input(
                        f"Please give feedback to {sender.name}. Press enter or type 'exit' to stop the conversation: "
                    )
                    no_human_input_msg = "NO HUMAN INPUT RECEIVED." if not reply else ""
                    # if the human input is empty, and the message is a termination message, then we will terminate the conversation
                    reply = reply or "exit"

        # print the no_human_input_msg
        if no_human_input_msg:
            print(colored(f"\n>>>>>>>> {no_human_input_msg}", "red"), flush=True)

        # stop the conversation
        if reply == "exit":
            # reset the consecutive_auto_reply_counter
            self._consecutive_auto_reply_counter[sender] = 0
            return True, None

        # send the human reply
        if reply or self._max_consecutive_auto_reply_dict[sender] == 0:
            # reset the consecutive_auto_reply_counter
            self._consecutive_auto_reply_counter[sender] = 0
            return True, reply

        # increment the consecutive_auto_reply_counter
        self._consecutive_auto_reply_counter[sender] += 1
        if self.human_input_mode != "NEVER":
            print(colored("\n>>>>>>>> USING AUTO REPLY...", "red"), flush=True)

        return False, None

    async def generate_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        exclude: Optional[List[Callable]] = None,
    ) -> Union[str, Dict, None]:
        """Reply based on the conversation history and the sender.

        Either messages or sender must be provided.
        Register a reply_func with `None` as one trigger for it to be activated when `messages` is non-empty and `sender` is `None`.
        Use registered auto reply functions to generate replies.
        By default, the following functions are checked in order:
        1. check_termination_and_human_reply
        2. generate_function_call_reply
        3. generate_code_execution_reply
        4. generate_oai_reply
        Every function returns a tuple (final, reply).
        When a function returns final=False, the next function will be checked.
        So by default, termination and human reply will be checked first.
        If not terminating and human reply is skipped, execute function or code and return the result.
        AI replies are generated only when no code execution is performed.

        Args:
            messages: a list of messages in the conversation history.
            default_reply (str or dict): default reply.
            sender: sender of an Agent instance.
            exclude: a list of functions to exclude.

        Returns:
            str or dict or None: reply. None if no reply is generated.
        ---------------------------------------------------------------
        """

        if all((messages is None, sender is None)):
            error_msg = f"Either {messages=} or {sender=} must be provided."
            logger.error(error_msg)
            raise AssertionError(error_msg)

        if messages is None:
            messages = self._oai_messages[sender]

        for reply_func_tuple in self._reply_func_list:
            reply_func = reply_func_tuple["reply_func"]
            if exclude and reply_func in exclude:
                continue
            if self._match_trigger(reply_func_tuple["trigger"], sender):
                if asyncio.coroutines.iscoroutinefunction(reply_func):
                    # print("messages : ", messages)
                    final, reply = await reply_func(self, messages=messages, sender=sender,
                                                    config=reply_func_tuple["config"])
                else:
                    final, reply = reply_func(self, messages=messages, sender=sender, config=reply_func_tuple["config"])
                if final:
                    return reply
        return self._default_auto_reply

    async def a_generate_reply(
        self,
        messages: Optional[List[Dict]] = None,
        sender: Optional[Agent] = None,
        exclude: Optional[List[Callable]] = None,
    ) -> Union[str, Dict, None]:
        """(async) Reply based on the conversation history and the sender.

        Either messages or sender must be provided.
        Register a reply_func with `None` as one trigger for it to be activated when `messages` is non-empty and `sender` is `None`.
        Use registered auto reply functions to generate replies.
        By default, the following functions are checked in order:
        1. check_termination_and_human_reply
        2. generate_function_call_reply
        3. generate_code_execution_reply
        4. generate_oai_reply
        Every function returns a tuple (final, reply).
        When a function returns final=False, the next function will be checked.
        So by default, termination and human reply will be checked first.
        If not terminating and human reply is skipped, execute function or code and return the result.
        AI replies are generated only when no code execution is performed.

        Args:
            messages: a list of messages in the conversation history.
            default_reply (str or dict): default reply.
            sender: sender of an Agent instance.
            exclude: a list of functions to exclude.

        Returns:
            str or dict or None: reply. None if no reply is generated.
        """
        if all((messages is None, sender is None)):
            error_msg = f"Either {messages=} or {sender=} must be provided."
            logger.error(error_msg)
            raise AssertionError(error_msg)

        if messages is None:
            messages = self._oai_messages[sender]

        for reply_func_tuple in self._reply_func_list:
            reply_func = reply_func_tuple["reply_func"]
            if exclude and reply_func in exclude:
                continue
            if self._match_trigger(reply_func_tuple["trigger"], sender):
                if asyncio.coroutines.iscoroutinefunction(reply_func):
                    final, reply = await reply_func(
                        self, messages=messages, sender=sender, config=reply_func_tuple["config"]
                    )
                else:
                    final, reply = reply_func(self, messages=messages, sender=sender, config=reply_func_tuple["config"])
                if final:
                    return reply
        return self._default_auto_reply

    def _match_trigger(self, trigger, sender):
        """Check if the sender matches the trigger.
        """

        if trigger is None:
            return sender is None
        elif isinstance(trigger, str):
            return trigger == sender.name
        elif isinstance(trigger, type):
            return isinstance(sender, trigger)
        elif isinstance(trigger, Agent):
            return trigger == sender
        elif isinstance(trigger, Callable):
            return trigger(sender)
        elif isinstance(trigger, list):
            return any(self._match_trigger(t, sender) for t in trigger)
        else:
            raise ValueError(f"Unsupported trigger type: {type(trigger)}")

    def get_human_input(self, prompt: str) -> str:
        """Get human input.

        Override this method to customize the way to get human input.

        Args:
            prompt (str): prompt for the human input.

        Returns:
            str: human input.
        """
        reply = input(prompt)
        return reply

    def run_code(self, code, **kwargs):
        """Run the code and return the result.

        Override this function to modify the way to run the code.
        Args:
            code (str): the code to be executed.
            **kwargs: other keyword arguments.

        Returns:
            A tuple of (exitcode, logs, image).
            exitcode (int): the exit code of the code execution.
            logs (str): the logs of the code execution.
            image (str or None): the docker image used for the code execution.
        """
        return execute_code(code, **kwargs)

    def execute_code_blocks(self, code_blocks):
        """Execute the code blocks and return the result."""
        logs_all = ""
        for i, code_block in enumerate(code_blocks):
            lang, code = code_block
            if not lang:
                lang = infer_lang(code)
            print(
                colored(
                    f"\n>>>>>>>> EXECUTING CODE BLOCK {i} (inferred language is {lang})...",
                    "red",
                ),
                flush=True,
            )
            if lang in ["bash", "shell", "sh"]:
                exitcode, logs, image = self.run_code(code, lang=lang, **self._code_execution_config)
            elif lang in ["python", "Python"]:
                if code.startswith("# filename: "):
                    filename = code[11: code.find("\n")].strip()
                else:
                    filename = None
                exitcode, logs, image = self.run_code(
                    code,
                    lang="python",
                    filename=filename,
                    **self._code_execution_config,
                )
            else:
                # In case the language is not supported, we return an error message.
                exitcode, logs, image = (
                    1,
                    f"unknown language {lang}",
                    None,
                )
                # raise NotImplementedError
            if image is not None:
                self._code_execution_config["use_docker"] = image
            logs_all += "\n" + logs
            if exitcode != 0:
                return exitcode, logs_all
        return exitcode, logs_all

    @staticmethod
    def _format_json_str(jstr):
        """Remove newlines outside of quotes, and handle JSON escape sequences.

        1. this function removes the newline in the query outside of quotes otherwise json.loads(s) will fail.
            Ex 1:
            "{\n"tool": "python",\n"query": "print('hello')\nprint('world')"\n}" -> "{"tool": "python","query": "print('hello')\nprint('world')"}"
            Ex 2:
            "{\n  \"location\": \"Boston, MA\"\n}" -> "{"location": "Boston, MA"}"

        2. this function also handles JSON escape sequences inside quotes,
            Ex 1:
            '{"args": "a\na\na\ta"}' -> '{"args": "a\\na\\na\\ta"}'
        """
        result = []
        inside_quotes = False
        last_char = " "
        for char in jstr:
            if last_char != "\\" and char == '"':
                inside_quotes = not inside_quotes
            last_char = char
            if not inside_quotes and char == "\n":
                continue
            if inside_quotes and char == "\n":
                char = "\\n"
            if inside_quotes and char == "\t":
                char = "\\t"
            result.append(char)
        return "".join(result)

    async def execute_function(self, func_call):
        """Execute a function call and return the result.

        Override this function to modify the way to execute a function call.

        Args:
            func_call: a dictionary extracted from openai message at key "function_call" with keys "name" and "arguments".

        Returns:
            A tuple of (is_exec_success, result_dict).
            is_exec_success (boolean): whether the execution is successful.
            result_dict: a dictionary with keys "name", "role", and "content". Value of "role" is "function".
        """
        func_name = func_call.get("name", "")
        func = self._function_map.get(func_name, None)

        is_exec_success = False
        if func is not None:
            # Extract arguments from a json-like string and put it into a dict.
            input_string = self._format_json_str(func_call.get("arguments", "{}"))
            try:
                arguments = json.loads(input_string)
            except json.JSONDecodeError as e:
                arguments = None
                content = f"Error: {e}\n You argument should follow json format."

            # Try to execute the function
            if arguments is not None:
                print(
                    colored(f"\n>>>>>>>> EXECUTING FUNCTION {func_name}...", "magenta"),
                    flush=True,
                )
                try:
                    if asyncio.coroutines.iscoroutinefunction(func):
                        content = await func(**arguments)
                    else:
                        content = func(**arguments)
                    is_exec_success = True
                except Exception as e:
                    content = f"Error: {e}"
        else:
            content = f"Error: Function {func_name} not found."

        return is_exec_success, {
            "name": func_name,
            "role": "function",
            "content": str(content),
        }

    def generate_init_message(self, **context) -> Union[str, Dict]:
        """Generate the initial message for the agent.

        Override this function to customize the initial message based on user's request.
        If not overriden, "message" needs to be provided in the context.
        """
        return context["message"]

    async def register_function(self, function_map: Dict[str, Callable]):
        """Register functions to the agent.

        Args:
            function_map: a dictionary mapping function names to functions.
        """
        self._function_map.update(function_map)

    async def ask_user(self, q_str):
        try:
            result_message = {
                'state': 200,
                'receiver': 'user',
                'data': {
                    'data_type': 'answer',
                    'content': q_str
                }
            }

            send_json_str = json.dumps(result_message)
            await self.outgoing.put(send_json_str)

        except Exception as e:
            traceback.print_exc()
            logger.error("from user:[{}".format(self.user_name) + "] , " + "error:" + str(e))

        # return "i have no question."
        return None

    def regex_fix_date_format(self, code_blocks):
        # fix mysql generate %%Y %%m %%d code :list
        pattern1 = r"%s"
        patterns_replacements = [
            (r"%%Y-%%m-%%d %%H", "%Y-%m-%d %H"),
            (r"%%Y-%%m-%%d", "%Y-%m-%d"),
            (r"%%Y-%%m", "%Y-%m"),
            (r"%%H", "%H"),
            (r"%%Y", "%Y"),
            (r"%%Y-%%m-%%d %%H:%%i", "%Y-%m-%d %H:%i"),
            (r"%%Y-%%m-%%d %%H:%%i:%%s", "%Y-%m-%d %H:%i:%s")]

        if re.search(pattern1, str(code_blocks)):
            for pattern, replacement in patterns_replacements:
                code_blocks = [(language, re.sub(replacement, pattern, code)) for language, code in code_blocks]
        else:
            for pattern, replacement in patterns_replacements:
                code_blocks = [(language, re.sub(pattern, replacement, code)) for language, code in code_blocks]

        return code_blocks
