import traceback
import json
from ai.backend.util.write_log import logger
from ai.backend.base_config import CONFIG
from ai.backend.util import database_util
from .analysis import Analysis
import re
import ast
from ai.agents.agentchat import AssistantAgent
from ai.backend.util import base_util

max_retry_times = CONFIG.max_retry_times


class AnalysisMysql(Analysis):

    async def deal_question(self, json_str, message):
        """
        Process mysql data source and select the corresponding workflow
        """
        result = {'state': 200, 'data': {}, 'receiver': ''}
        q_sender = json_str['sender']
        q_data_type = json_str['data']['data_type']
        print('q_data_type : ', q_data_type)
        q_str = json_str['data']['content']

        print("self.agent_instance_util.api_key_use :", self.agent_instance_util.api_key_use)
        if not self.agent_instance_util.api_key_use:
            re_check = await self.check_api_key()
            print('re_check : ', re_check)
            if not re_check:
                return

        if q_sender == 'user':
            if q_data_type == 'question':
                # print("agent_instance_util.base_message :", self.agent_instance_util.base_message)
                if self.agent_instance_util.base_message is not None:
                    await self.start_chatgroup(q_str)

                else:
                    await self.put_message(500, receiver=CONFIG.talker_user, data_type=CONFIG.type_answer,
                                           content=self.error_miss_data)
        elif q_sender == 'bi':
            if q_data_type == CONFIG.type_comment:
                await self.check_data_base(q_str)
            elif q_data_type == CONFIG.type_comment_first:
                if json_str.get('data').get('language_mode'):
                    q_language_mode = json_str['data']['language_mode']
                    if q_language_mode == CONFIG.language_chinese or q_language_mode == CONFIG.language_english or q_language_mode == CONFIG.language_japanese:
                        self.set_language_mode(q_language_mode)
                        self.agent_instance_util.set_language_mode(q_language_mode)

                if CONFIG.database_model == 'online':
                    databases_id = json_str['data']['databases_id']
                    db_id = str(databases_id)
                    obj = database_util.Main(db_id)
                    if_suss, db_info = obj.run()
                    if if_suss:
                        self.agent_instance_util.base_mysql_info = ' When connecting to the database, be sure to bring the port. This is mysql database info :' + '\n' + str(
                            db_info)
                        self.agent_instance_util.set_base_message(q_str)
                        self.agent_instance_util.db_id = db_id


                else:
                    self.agent_instance_util.set_base_message(q_str)

                await self.get_data_desc(q_str)
            elif q_data_type == CONFIG.type_comment_second:
                if json_str.get('data').get('language_mode'):
                    q_language_mode = json_str['data']['language_mode']
                    if q_language_mode == CONFIG.language_chinese or q_language_mode == CONFIG.language_english or q_language_mode == CONFIG.language_japanese:
                        self.set_language_mode(q_language_mode)
                        self.agent_instance_util.set_language_mode(q_language_mode)

                if CONFIG.database_model == 'online':
                    databases_id = json_str['data']['databases_id']
                    db_id = str(databases_id)
                    print("db_id:", db_id)
                    obj = database_util.Main(db_id)
                    if_suss, db_info = obj.run()
                    if if_suss:
                        self.agent_instance_util.base_mysql_info = '  When connecting to the database, be sure to bring the port. This is mysql database info :' + '\n' + str(
                            db_info)
                        self.agent_instance_util.set_base_message(q_str)
                        self.agent_instance_util.db_id = db_id
                else:
                    self.agent_instance_util.set_base_message(q_str)

                await self.put_message(200, receiver=CONFIG.talker_bi, data_type=CONFIG.type_comment_second,
                                       content='')
            elif q_data_type == 'mysql_code' or q_data_type == 'chart_code' or q_data_type == 'delete_chart' or q_data_type == 'ask_data':
                self.delay_messages['bi'][q_data_type].append(message)
                print("delay_messages : ", self.delay_messages)
                return
        else:
            print('error : q_sender is not user or bi')
            await self.put_message(500, receiver=CONFIG.talker_bi, data_type=CONFIG.type_comment_second,
                                   content='error : q_sender is not user or bi')

    async def task_base(self, qustion_message):
        """ Task type: mysql data analysis"""
        try:
            error_times = 0
            for i in range(max_retry_times):
                try:
                    base_mysql_assistant = self.get_agent_base_mysql_assistant()
                    python_executor = self.agent_instance_util.get_agent_python_executor()

                    # 修改 python_executor 的 is_termination_msg 函数，使其不会将 "TERMINATE" 视为终止消息
                    def custom_is_termination_msg(message_dict):
                        # 始终返回 False，不将任何消息视为终止消息
                        return False

                    # 保存原始的 is_termination_msg 函数
                    original_executor_is_termination_msg = python_executor._is_termination_msg
                    python_executor._is_termination_msg = custom_is_termination_msg

                    await python_executor.initiate_chat(
                        base_mysql_assistant,
                        message=self.agent_instance_util.base_message + '\n' + self.question_ask + '\n' + str(
                            qustion_message),
                    )

                    # 恢复原始的 is_termination_msg 函数
                    python_executor._is_termination_msg = original_executor_is_termination_msg

                    answer_message = python_executor.chat_messages[base_mysql_assistant]
                    print("answer_message: ", answer_message)

                    for j in range(len(answer_message)):
                        answer_mess = answer_message[len(answer_message) - 1 - j]
                        # print("answer_mess :", answer_mess)
                        if answer_mess.get('content'):
                            # 移除 "TERMINATE" 并返回内容
                            content = answer_mess['content'].replace("TERMINATE", "").strip()
                            if content:
                                print("answer_mess['content'] ", content)
                                return content

                except Exception as e:
                    traceback.print_exc()
                    logger.error("from user:[{}".format(self.user_name) + "] , " + "error: " + str(e))
                    error_times = error_times + 1

            if error_times >= max_retry_times:
                return self.error_message_timeout

        except Exception as e:
            traceback.print_exc()
            logger.error("from user:[{}".format(self.user_name) + "] , " + "error: " + str(e))

        return self.agent_instance_util.data_analysis_error

    def get_agent_base_mysql_assistant(self):
        """ Basic Agent, processing mysql data source """
        base_mysql_assistant = AssistantAgent(
            name="base_mysql_assistant",
            system_message="""You are a helpful AI assistant.
                  Solve tasks using your coding and language skills.
                  In the following cases, suggest python code (in a python coding block) for the user to execute.
                      1. When you need to collect info, use the code to output the info you need, for example, browse or search the web, download/read a file, print the content of a webpage or a file, get the current date/time, check the operating system. After sufficient info is printed and the task is ready to be solved based on your language skill, you can solve the task by yourself.
                      2. When you need to perform some task with code, use the code to perform the task and output the result. Finish the task smartly.
                  Solve the task step by step if you need to. If a plan is not provided, explain your plan first. Be clear which step uses code, and which step uses your language skill.
                  When using code, you must indicate the script type in the code block. The user cannot provide any other feedback or perform any other action beyond executing the code you suggest. The user can't modify your code. So do not suggest incomplete code which requires users to modify. Don't use a code block if it's not intended to be executed by the user.
                  If you want the user to save the code in a file before executing it, put # filename: <filename> inside the code block as the first line. Don't include multiple code blocks in one response. Do not ask users to copy and paste the result. Instead, use 'print' function for the output when relevant. Check the execution result returned by the user.
                  If the result indicates there is an error, fix the error and output the code again. Suggest the full code instead of partial code or code changes. If the error can't be fixed or if the task is not solved even after the code is executed successfully, analyze the problem, revisit your assumption, collect additional info you need, and think of a different approach to try.
                  When you find an answer, verify the answer carefully. Include verifiable evidence in your response if possible.
                  In any case (even if I ask you to output an html file), please output the results directly and do not save them to a file.
                  IMPORTANT: Do not add "TERMINATE" at the end of your messages. This will cause issues with the system.
                  When you find an answer,  You are a report analysis, you have the knowledge and skills to turn raw data into information and insight, which can be used to make business decisions.include your analysis in your reply.
                  Be careful to avoid using mysql special keywords in mysql code.
                  """ + '\n' + self.agent_instance_util.base_mysql_info + '\n' + CONFIG.python_base_dependency + '\n' + self.agent_instance_util.quesion_answer_language,
            human_input_mode="NEVER",
            user_name=self.user_name,
            websocket=self.websocket,
            llm_config={
                "config_list": self.agent_instance_util.config_list_gpt4_turbo,
                "request_timeout": CONFIG.request_timeout,
            },
            openai_proxy=self.agent_instance_util.openai_proxy,
        )
        return base_mysql_assistant

    async def task_generate_echart(self, qustion_message):
        try:
            base_mess = []
            report_demand_list = []
            is_chart=False
            error_times = 0
            use_cache = True
            for i in range(max_retry_times):
                try:
                    mysql_echart_assistant = self.agent_instance_util.get_agent_mysql_echart_assistant(
                        use_cache=use_cache)
                    python_executor = self.agent_instance_util.get_agent_python_executor()

                    # 修改 python_executor 的 is_termination_msg 函数，使其不会将 "TERMINATE" 视为终止消息
                    def custom_is_termination_msg(message_dict):
                        # 始终返回 False，不将任何消息视为终止消息
                        return False

                    # 保存原始的 is_termination_msg 函数
                    original_executor_is_termination_msg = python_executor._is_termination_msg
                    python_executor._is_termination_msg = custom_is_termination_msg

                    await python_executor.initiate_chat(
                        mysql_echart_assistant,
                        message=self.agent_instance_util.base_message + '\n' + self.question_ask + '\n' + str(
                            qustion_message),
                    )

                    # 恢复原始的 is_termination_msg 函数
                    python_executor._is_termination_msg = original_executor_is_termination_msg

                    answer_message = mysql_echart_assistant.chat_messages[python_executor]
                    # 保存完整的对话历史，而不仅仅是最后一条消息
                    base_mess = []
                    # 保存所有的对话消息，包括问题和回答
                    message_to_assistant = self.agent_instance_util.base_message + '\n' + self.question_ask + '\n' + str(qustion_message)
                    base_mess.append({"role": "user", "content": message_to_assistant})
                    for msg in answer_message:
                        base_mess.append(msg)
                    if str(answer_message).__contains__('图像已生成'):
                        is_chart=True
                    else:
                        is_chart=False
                    break
                except Exception as e:
                    traceback.print_exc()
                    logger.error("from user:[{}".format(self.user_name) + "] , " + "error: " + str(e))
                    error_times = error_times + 1
                    use_cache = False

            if error_times >= max_retry_times:
                return self.error_message_timeout

            logger.info(
                "from user:[{}".format(self.user_name) + "] , " + "，report_demand_list" + str(report_demand_list))
            error_times = 0
            for i in range(max_retry_times):
                try:
                    planner_user = self.agent_instance_util.get_agent_planner_user()
                    analyst = self.agent_instance_util.get_agent_analyst()

                    question_supplement = 'Please make an analysis and summary in English, including which charts were generated, and briefly introduce the contents of these charts. IMPORTANT: Do not add "TERMINATE" at the end of your message.'
                    if self.language_mode == CONFIG.language_chinese:
                        if is_chart:
                            question_supplement = ' 请用中文，详细介绍已生成图表中的数据内容,分析完毕后即结束任务. 重要提示：请不要在消息末尾添加"TERMINATE"。'
                        else:
                            question_supplement = ' 请用中文，从上诉对话中分析总结出问题的答案. 重要提示：请不要在消息末尾添加"TERMINATE"。'
                    elif self.language_mode == CONFIG.language_japanese:
                        if is_chart:
                            question_supplement = ' 生成されたグラフのデータ内容について、簡単に日本語で説明してください。重要：メッセージの最後に「TERMINATE」を追加しないでください。'
                        else:
                            question_supplement = ' 上記の対話から問題の答えを分析し、日本語で要約してください。重要：メッセージの最後に「TERMINATE」を追加しないでください。'

                    # 构建发送给 Analyst 的消息
                    message_to_analyst = str(base_mess) + '\n' + self.question_ask + '\n' + question_supplement

                    # 使用现有的 analyst 实例，不尝试修改其系统消息
                    # 设置 human_input_mode 为 "NEVER"
                    planner_user.human_input_mode = "NEVER"

                    # 设置自定义的 is_termination_msg 函数
                    def custom_is_termination_msg(message_dict):
                        return False

                    # 保存原始的 is_termination_msg 函数
                    original_analyst_is_termination_msg = analyst._is_termination_msg
                    original_planner_is_termination_msg = planner_user._is_termination_msg

                    # 临时设置 is_termination_msg 函数
                    analyst._is_termination_msg = custom_is_termination_msg
                    planner_user._is_termination_msg = custom_is_termination_msg

                    try:
                        # 在消息中添加提示，而不是修改系统消息
                        message_with_warning = message_to_analyst + "\n\nIMPORTANT: Do not add 'TERMINATE' at the end of your messages. This will cause issues with the system."

                        # 发送消息并获取回复
                        await planner_user.send(message_with_warning, analyst, request_reply=True)

                        # 获取回复消息
                        # 检查是否有 last_message 方法
                        if hasattr(planner_user, 'last_message') and callable(getattr(planner_user, 'last_message')):
                            last_message = planner_user.last_message(analyst)
                        else:
                            # 如果没有 last_message 方法，尝试从 chat_messages 获取
                            if hasattr(planner_user, 'chat_messages') and analyst in planner_user.chat_messages:
                                messages = planner_user.chat_messages[analyst]
                                last_message = messages[-1] if messages else None
                            else:
                                last_message = None
                    finally:
                        # 恢复原始的 is_termination_msg 函数
                        analyst._is_termination_msg = original_analyst_is_termination_msg
                        planner_user._is_termination_msg = original_planner_is_termination_msg

                    # 提取回复内容
                    if last_message is not None:
                        if isinstance(last_message, dict) and "content" in last_message:
                            answer_message = last_message["content"]
                        else:
                            answer_message = str(last_message)
                    else:
                        # 如果无法获取回复，返回一个默认消息
                        answer_message = "无法获取分析结果，请查看图表数据。"

                    # Remove "TERMINATE" from the answer message
                    answer_message = answer_message.replace("TERMINATE", "")
                    return answer_message

                except Exception as e:
                    traceback.print_exc()
                    logger.error("from user:[{}".format(self.user_name) + "] , " + "error: " + str(e))
                    error_times = error_times + 1

            if error_times == max_retry_times:
                return self.error_message_timeout

        except Exception as e:
            traceback.print_exc()
            logger.error("from user:[{}".format(self.user_name) + "] , " + "error: " + str(e))
        return self.agent_instance_util.data_analysis_error
