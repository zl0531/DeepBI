import traceback
import json
import re
import ast
import os
import sys
import pandas as pd
import psycopg2
from ai.backend.util.write_log import logger
from ai.backend.base_config import CONFIG
from ai.backend.util import database_util
from .analysis import Analysis
from ai.agents.agentchat import AssistantAgent
from ai.backend.util import base_util
try:
    from sample_data_fetcher import SampleDataFetcher
    SAMPLE_DATA_FETCHER_AVAILABLE = True
except ImportError:
    SAMPLE_DATA_FETCHER_AVAILABLE = False

language_chinese = CONFIG.language_chinese
max_retry_times = CONFIG.max_retry_times


class AnalysisPostgresql(Analysis):
    async def deal_question(self, json_str, message):
        """ Process the postgresql data source and select the corresponding workflow """
        result = {'state': 200, 'data': {}, 'receiver': ''}
        q_sender = json_str['sender']
        q_data_type = json_str['data']['data_type']
        q_str = json_str['data']['content']

        if not self.agent_instance_util.api_key_use:
            re_check = await self.check_api_key()
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
            if q_data_type == 'mysql_comment':
                await self.check_data_base(q_str)
            elif q_data_type == 'mysql_comment_first':
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
                        self.agent_instance_util.base_postgresql_info = '  When connecting to the database, be sure to bring the port. This is postgresql database info :' + '\n' + str(
                            db_info)
                        # self.agent_instance_util.base_message = str(q_str)
                        self.agent_instance_util.set_base_message(q_str)

                        self.agent_instance_util.db_id = db_id

                else:
                    # self.agent_instance_util.base_message = str(q_str)
                    self.agent_instance_util.set_base_message(q_str)

                # result['data']['content'] = json_str['data']['content']

                await self.get_data_desc(q_str)
            elif q_data_type == 'mysql_comment_second':
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
                        self.agent_instance_util.base_postgresql_info = '  When connecting to the database, be sure to bring the port. This is postgresql database info :' + '\n' + str(
                            db_info)
                        # self.agent_instance_util.base_message = str(q_str)
                        self.agent_instance_util.set_base_message(q_str)

                        self.agent_instance_util.db_id = db_id

                else:
                    # self.agent_instance_util.base_message = str(q_str)
                    self.agent_instance_util.set_base_message(q_str)

                # result = ask_commentengineer(q_str, result)
                # result['data']['content'] = await get_data_desc(agent_instance_util, q_str)

                result['receiver'] = 'bi'
                result['data']['data_type'] = 'mysql_comment_second'
                # result['data']['content'] = json_str['data']['content']
                consume_output = json.dumps(result)
                await self.outgoing.put(consume_output)
            elif q_data_type == 'mysql_code' or q_data_type == 'chart_code' or q_data_type == 'delete_chart' or q_data_type == 'ask_data':
                self.delay_messages['bi'][q_data_type].append(message)
                print("delay_messages : ", self.delay_messages)
                return

    async def task_base(self, qustion_message):
        """ Task type:  data analysis"""
        try:
            error_times = 0
            for i in range(max_retry_times):
                try:
                    base_mysql_assistant = self.get_agent_base_postgresql_assistant()
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

    def get_agent_base_postgresql_assistant(self):
        """ Basic Agent, processing postgresql data source"""
        base_postgresql_assistant = AssistantAgent(
            name="base_postgresql_assistant",
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
                         IMPORTANT: Do not add "TERMINATE" at the end of your messages. This will cause issues with the system.
                         When you find an answer,  You are a report analysis, you have the knowledge and skills to turn raw data into information and insight, which can be used to make business decisions.include your analysis in your reply.

                         Be careful to avoid using postgresql special keywords in postgresql code.

                         """ + '\n' + self.agent_instance_util.base_postgresql_info + '\n' + CONFIG.python_base_dependency + '\n' + self.agent_instance_util.quesion_answer_language,
            human_input_mode="NEVER",
            user_name=self.user_name,
            websocket=self.websocket,
            llm_config={
                "config_list": self.agent_instance_util.config_list_gpt4_turbo,
                "request_timeout": CONFIG.request_timeout,
            },
            openai_proxy=self.agent_instance_util.openai_proxy,
        )
        return base_postgresql_assistant

    async def task_generate_echart(self, qustion_message):
        """ Task type: postgresql echart code block"""
        try:
            base_content = []
            base_mess = []
            report_demand_list = []
            json_str = ""
            error_times = 0
            use_cache = True
            query_enhanced = False
            for i in range(max_retry_times):
                try:
                    postgresql_echart_assistant = self.agent_instance_util.get_agent_postgresql_echart_assistant(
                        use_cache=use_cache)
                    python_executor = self.agent_instance_util.get_agent_python_executor()

                    # 修改 python_executor 的 is_termination_msg 函数，使其不会将 "TERMINATE" 视为终止消息
                    def custom_is_termination_msg(message_dict):
                        # 始终返回 False，不将任何消息视为终止消息
                        return False

                    # 保存原始的 is_termination_msg 函数
                    original_executor_is_termination_msg = python_executor._is_termination_msg
                    python_executor._is_termination_msg = custom_is_termination_msg

                    # 构建发送给 LLM 的消息
                    message_to_assistant = self.agent_instance_util.base_message + '\n' + self.question_ask + '\n' + str(qustion_message)

                    # Fetch sample data for tables
                    try:
                        # Create connection parameters
                        connection_params = {
                            "dbname": "postgres",
                            "user": "postgres",
                            "password": "",
                            "host": "postgres",
                            "port": "5432"
                        }

                        # Connect to the database
                        connection = psycopg2.connect(**connection_params)

                        # Get sample data for tables mentioned in the message
                        tables = []
                        if isinstance(qustion_message, dict) and 'table_desc' in qustion_message:
                            for table in qustion_message['table_desc']:
                                if 'table_name' in table:
                                    tables.append(table['table_name'])

                        if tables:
                            sample_data_sections = []
                            for table_name in tables:
                                try:
                                    # Simple query to get a few rows
                                    query = f"SELECT * FROM {table_name} LIMIT 5"
                                    df = pd.read_sql(query, con=connection)

                                    # Convert to string
                                    sample_data = df.to_string(index=False)

                                    # Add to sections
                                    sample_data_sections.append(f"Sample data for {table_name}:\n{sample_data}")

                                    # Get important columns from the table description
                                    important_columns = []
                                    if isinstance(qustion_message, dict) and 'table_desc' in qustion_message:
                                        for table_desc in qustion_message['table_desc']:
                                            if 'table_name' in table_desc and table_desc['table_name'] == table_name and 'field_desc' in table_desc:
                                                for field in table_desc['field_desc']:
                                                    # Check if the field comment contains parentheses with abbreviations
                                                    if 'name' in field and 'comment' in field and '（' in field['comment'] and '）' in field['comment']:
                                                        important_columns.append(field['name'])

                                    # If we found important columns, get their distinct values
                                    if important_columns:
                                        for column in important_columns:
                                            try:
                                                # Get distinct values for the column
                                                distinct_query = f"SELECT DISTINCT {column} FROM {table_name}"
                                                distinct_df = pd.read_sql(distinct_query, con=connection)
                                                distinct_values = distinct_df[column].tolist()

                                                if distinct_values:
                                                    # Add a special note about the column values
                                                    sample_data_sections.append(f"\nIMPORTANT: The actual values in the {column} column are: {', '.join([str(v) for v in distinct_values])}. " +
                                                                              f"When writing SQL queries, use these exact values, not translations or abbreviations.")
                                            except Exception as e:
                                                logger.error(f"Error fetching distinct values for {column}: {str(e)}")
                                except Exception as e:
                                    logger.error(f"Error fetching sample data for {table_name}: {str(e)}")

                            # Close connection
                            connection.close()

                            # Add sample data to message
                            if sample_data_sections:
                                sample_data_text = "\n\nHere are some sample rows from the tables to help you understand the actual data:\n\n"
                                sample_data_text += "\n\n".join(sample_data_sections)
                                message_to_assistant += sample_data_text
                                logger.info(f"Added sample data for tables: {', '.join(tables)}")
                    except Exception as e:
                        logger.error(f"Error adding sample data: {str(e)}")

                    # 添加日志，查看发送给 postgresql_echart_assistant 的消息内容
                    print("Message to postgresql_echart_assistant: ", message_to_assistant)
                    logger.info("Message to postgresql_echart_assistant: " + message_to_assistant)

                    # Add general instructions about using exact values from the database
                    message_to_assistant += "\n\nIMPORTANT: When writing SQL queries, always use the exact values from the database. "
                    message_to_assistant += "Do not translate column values or use abbreviations. "
                    message_to_assistant += "For example, if a column contains values like 'Battery Electric Vehicle (BEV)', use that exact string in your queries, "
                    message_to_assistant += "not translations like '电池电动汽车（BEV）' or abbreviations like 'BEV'."

                    await python_executor.initiate_chat(
                        postgresql_echart_assistant,
                        message=message_to_assistant,
                    )

                    # 恢复原始的 is_termination_msg 函数
                    python_executor._is_termination_msg = original_executor_is_termination_msg

                    answer_message = postgresql_echart_assistant.chat_messages[python_executor]

                    # 添加日志，查看从 postgresql_echart_assistant 收到的消息内容
                    print("Messages from postgresql_echart_assistant: ", answer_message)
                    logger.info("Messages from postgresql_echart_assistant: " + str(answer_message))

                    for answer_mess in answer_message:
                        # print("answer_mess :", answer_mess)
                        if answer_mess['content']:
                            if str(answer_mess['content']).__contains__('execution succeeded'):

                                answer_mess_content = str(answer_mess['content']).replace('\n', '')

                                # Replace Chinese terms with English terms in SQL queries and Python code
                                answer_mess_content = answer_mess_content.replace("'电池电动汽车（BEV）'", "'Battery Electric Vehicle (BEV)'")
                                answer_mess_content = answer_mess_content.replace("'插电式混合动力电动车（PHEV）'", "'Plug-in Hybrid Electric Vehicle (PHEV)'")
                                answer_mess_content = answer_mess_content.replace('"电池电动汽车（BEV）"', '"Battery Electric Vehicle (BEV)"')
                                answer_mess_content = answer_mess_content.replace('"插电式混合动力电动车（PHEV）"', '"Plug-in Hybrid Electric Vehicle (PHEV)"')

                                # Also fix the Python code that might be generated
                                # Fix SQL queries in Python code
                                if "electric_vehicle_type" in answer_mess_content:
                                    # Fix Python code with regex to handle various formats
                                    answer_mess_content = re.sub(
                                        r"(['\"])电池电动汽车（BEV）(['\"])",
                                        r"\1Battery Electric Vehicle (BEV)\2",
                                        answer_mess_content
                                    )
                                    answer_mess_content = re.sub(
                                        r"(['\"])插电式混合动力电动车（PHEV）(['\"])",
                                        r"\1Plug-in Hybrid Electric Vehicle (PHEV)\2",
                                        answer_mess_content
                                    )

                                    # Fix SQL queries in triple-quoted strings
                                    answer_mess_content = re.sub(
                                        r'(""".*?electric_vehicle_type\s*=\s*)[\'"]电池电动汽车（BEV）[\'"]',
                                        r"\1'Battery Electric Vehicle (BEV)'",
                                        answer_mess_content,
                                        flags=re.DOTALL
                                    )
                                    answer_mess_content = re.sub(
                                        r'(""".*?electric_vehicle_type\s*=\s*)[\'"]插电式混合动力电动车（PHEV）[\'"]',
                                        r"\1'Plug-in Hybrid Electric Vehicle (PHEV)'",
                                        answer_mess_content,
                                        flags=re.DOTALL
                                    )

                                    # Fix SQL queries with CASE WHEN statements
                                    answer_mess_content = re.sub(
                                        r"(CASE WHEN electric_vehicle_type\s*=\s*)['\"]电池电动汽车（BEV）['\"]",
                                        r"\1'Battery Electric Vehicle (BEV)'",
                                        answer_mess_content
                                    )
                                    answer_mess_content = re.sub(
                                        r"(CASE WHEN electric_vehicle_type\s*=\s*)['\"]插电式混合动力电动车（PHEV）['\"]",
                                        r"\1'Plug-in Hybrid Electric Vehicle (PHEV)'",
                                        answer_mess_content
                                    )

                                print("answer_mess: ", answer_mess)
                                # 添加日志，查看 python_executor 执行结果的消息内容
                                logger.info("Python executor result: " + str(answer_mess['content']))
                                match = re.search(
                                    r"\[.*\]", answer_mess_content.strip(), re.MULTILINE | re.IGNORECASE | re.DOTALL
                                )

                                if match:
                                    json_str = match.group()
                                print("json_str : ", json_str)
                                # report_demand_list = json.loads(json_str)

                                chart_code_str = str(json_str).replace('\n', '')

                                if len(chart_code_str) > 0:
                                    print("chart_code_str: ", chart_code_str)
                                    if base_util.is_json(chart_code_str):
                                        # report_demand_list = ast.literal_eval(chart_code_str)
                                        report_demand_list = json.loads(chart_code_str)

                                        print("report_demand_list: ", report_demand_list)

                                        for jstr in report_demand_list:
                                            if str(jstr).__contains__('echart_name') and str(jstr).__contains__(
                                                'echart_code'):
                                                base_content.append(jstr)
                                    else:
                                        report_demand_list = ast.literal_eval(chart_code_str)
                                        print("report_demand_list: ", report_demand_list)
                                        for jstr in report_demand_list:
                                            if str(jstr).__contains__('echart_name') and str(jstr).__contains__(
                                                'echart_code'):
                                                base_content.append(jstr)

                    print("base_content: ", base_content)
                    # 保存完整的对话历史，而不仅仅是最后一条消息
                    base_mess = []
                    # 保存所有的对话消息，包括问题和回答
                    base_mess.append({"role": "user", "content": message_to_assistant})
                    for msg in answer_message:
                        base_mess.append(msg)
                    # 添加日志，查看 base_mess 的内容
                    print("base_mess: ", base_mess)
                    logger.info("base_mess: " + str(base_mess))
                    break

                except Exception as e:
                    traceback.print_exc()
                    logger.error("from user:[{}".format(self.user_name) + "] , " + "error: " + str(e))
                    error_times = error_times + 1
                    use_cache = False

            if error_times >= max_retry_times:
                return self.error_message_timeout

            bi_proxy = self.agent_instance_util.get_agent_bi_proxy()
            is_chart = False
            for img_str in base_content:
                echart_name = img_str.get('echart_name')
                echart_code = img_str.get('echart_code')

                # 检查图表数据是否为空
                has_data = False
                if echart_code and 'series' in echart_code:
                    for series in echart_code['series']:
                        if series.get('data') and len(series['data']) > 0:
                            has_data = True
                            break

                # 如果图表数据为空，尝试使用更通用的方法查找数据
                if not has_data and echart_code and not query_enhanced:
                    # Set the flag to indicate we've tried to enhance the query
                    query_enhanced = True
                    print("Warning: Chart has empty data series, trying general approach")
                    logger.warning("Chart has empty data series: " + echart_name + ", trying general approach")

                    try:
                        # 导入查询增强器
                        import sys
                        import os

                        import json

                        # 创建工具模块的路径
                        utils_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "utils")
                        if not os.path.exists(utils_dir):
                            os.makedirs(utils_dir)

                        # 将查询增强器复制到utils目录
                        query_enhancer_path = os.path.join(utils_dir, "query_enhancer.py")
                        if not os.path.exists(query_enhancer_path):
                            try:
                                with open("/app/query_enhancer.py", "r") as src:
                                    with open(query_enhancer_path, "w") as dst:
                                        dst.write(src.read())
                            except FileNotFoundError:
                                # 如果文件不存在，创建一个基本的查询增强器
                                with open(query_enhancer_path, "w") as f:
                                    f.write("""
import re
import logging
import psycopg2
import pandas as pd
from difflib import SequenceMatcher

class QueryEnhancer:
    def __init__(self, connection_params):
        self.connection_params = connection_params

    def get_connection(self):
        return psycopg2.connect(**self.connection_params)

    def get_distinct_values(self, table_name, column_name):
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            cursor.execute(f"SELECT DISTINCT {column_name} FROM {table_name}")
            values = [row[0] for row in cursor.fetchall()]
            cursor.close()
            connection.close()
            return values
        except Exception as e:
            print(f"Error getting distinct values: {str(e)}")
            return []

    def similarity_score(self, a, b):
        return SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

    def find_best_matches(self, search_terms, candidates, threshold=0.6):
        matches = {}
        for term in search_terms:
            term_str = str(term).lower()
            exact_matches = [c for c in candidates if str(c).lower() == term_str]
            if exact_matches:
                matches[term] = exact_matches[0]
                continue
            contains_matches = [c for c in candidates if term_str in str(c).lower()]
            if contains_matches:
                matches[term] = sorted(contains_matches, key=lambda x: len(str(x)))[0]
                continue
            scores = [(c, self.similarity_score(term, c)) for c in candidates]
            best_matches = sorted(scores, key=lambda x: x[1], reverse=True)
            if best_matches and best_matches[0][1] >= threshold:
                matches[term] = best_matches[0][0]
            else:
                matches[term] = None
        return matches

    def extract_comparison_terms(self, query_text):
        quoted_terms = re.findall(r'"([^"]*)"', query_text)
        quoted_terms.extend(re.findall(r"'([^']*)'", query_text))
        compare_terms = []
        compare_patterns = [
            r'compare\\s+([^,]+)\\s+and\\s+([^,\\.]+)',
            r'对比\\s+([^,]+)\\s+和\\s+([^,\\.]+)',
            r'比较\\s+([^,]+)\\s+和\\s+([^,\\.]+)',
            r'between\\s+([^,]+)\\s+and\\s+([^,\\.]+)'
        ]
        for pattern in compare_patterns:
            matches = re.findall(pattern, query_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    compare_terms.extend(match)
                else:
                    compare_terms.append(match)
        all_terms = quoted_terms + compare_terms
        cleaned_terms = [term.strip() for term in all_terms if term.strip()]
        if not cleaned_terms:
            abbrev_terms = re.findall(r'\\(([A-Z]{2,})\\)', query_text)
            cleaned_terms.extend(abbrev_terms)
            cap_words = re.findall(r'\\b([A-Z][a-z]*(?:\\s+[A-Z][a-z]*)*)\\b', query_text)
            cleaned_terms.extend(cap_words)
        return list(set(cleaned_terms))

    def enhance_query(self, original_query, user_query_text, table_name, column_name):
        try:
            search_terms = self.extract_comparison_terms(user_query_text)
            print(f"Extracted search terms: {search_terms}")
            if not search_terms:
                return original_query, []
            actual_values = self.get_distinct_values(table_name, column_name)
            print(f"Found {len(actual_values)} distinct values in {column_name}")
            matches = self.find_best_matches(search_terms, actual_values)
            print(f"Term matches: {matches}")
            valid_matches = {term: value for term, value in matches.items() if value is not None}
            if not valid_matches:
                return original_query, []
            in_clause_pattern = r"IN\\s*\\([^\\)]+\\)"
            placeholders = ", ".join(["%s"] * len(valid_matches))
            actual_values = list(valid_matches.values())
            new_in_clause = f"IN ({', '.join(['%s'] * len(actual_values))})"
            enhanced_query = re.sub(in_clause_pattern, new_in_clause, original_query)
            return enhanced_query, actual_values
        except Exception as e:
            print(f"Error enhancing query: {str(e)}")
            return original_query, []

    def execute_enhanced_query(self, query, params, user_query_text, table_name, column_name):
        try:
            enhanced_query, actual_values = self.enhance_query(query, user_query_text, table_name, column_name)
            if not actual_values:
                connection = self.get_connection()
                df = pd.read_sql(query, con=connection, params=params)
                connection.close()
                return df
            connection = self.get_connection()
            df = pd.read_sql(enhanced_query, con=connection, params=actual_values)
            connection.close()
            return df
        except Exception as e:
            print(f"Error executing enhanced query: {str(e)}")
            try:
                connection = self.get_connection()
                df = pd.read_sql(query, con=connection, params=params)
                connection.close()
                return df
            except Exception as e2:
                print(f"Error executing original query: {str(e2)}")
                return pd.DataFrame()
""")

                        # 导入查询增强器
                        sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                        from ai.utils.query_enhancer import QueryEnhancer

                        # 分析图表代码，查找SQL查询
                        chart_code_str = json.dumps(echart_code)
                        sql_queries = re.findall(r'SELECT\s+.*?\s+FROM\s+.*?(?:;|$)', chart_code_str, re.IGNORECASE | re.DOTALL)

                        if sql_queries:
                            # 找到了SQL查询，尝试增强它
                            original_query = sql_queries[0]

                            # 提取表名和列名
                            table_match = re.search(r'FROM\s+([^\s,;]+)', original_query, re.IGNORECASE)
                            column_match = re.search(r'WHERE\s+([^\s=]+)\s+IN', original_query, re.IGNORECASE)

                            if table_match and column_match:
                                table_name = table_match.group(1)
                                column_name = column_match.group(1)

                                # 创建数据库连接参数
                                connection_params = {
                                    "dbname": "postgres",
                                    "user": "postgres",
                                    "password": "",
                                    "host": "postgres",
                                    "port": "5432"
                                }

                                # 初始化查询增强器
                                enhancer = QueryEnhancer(connection_params)

                                # 增强查询
                                enhanced_query, actual_values = enhancer.enhance_query(
                                    original_query,
                                    str(qustion_message),
                                    table_name,
                                    column_name
                                )

                                if actual_values:
                                    # 成功找到匹配的值，重新生成图表
                                    print(f"Found matching values: {actual_values}")
                                    logger.info(f"Found matching values: {actual_values}")

                                    # 替换原始SQL查询
                                    new_chart_code_str = chart_code_str.replace(original_query, enhanced_query)

                                    # 更新图表代码
                                    echart_code = json.loads(new_chart_code_str)
                                    has_data = True
                                    print("Successfully enhanced query using general approach")
                                    logger.info("Successfully enhanced query using general approach")

                    except Exception as e:
                        print(f"Error using general approach: {str(e)}")
                        logger.error(f"Error using general approach: {str(e)}")

                    # 如果通用方法失败或不适用，添加提示信息
                    if not has_data and echart_code:
                        # 如果图表有标题配置，添加"无数据"提示
                        if 'title' not in echart_code:
                            echart_code['title'] = {}

                        # 根据语言模式设置不同的提示文本
                        no_data_text = "No data available"
                        if self.language_mode == language_chinese:
                            no_data_text = "无数据"
                        elif self.language_mode == CONFIG.language_japanese:
                            no_data_text = "データなし"

                        if 'text' in echart_code['title']:
                            echart_code['title']['text'] += " (" + no_data_text + ")"
                        else:
                            echart_code['title']['text'] = echart_name + " (" + no_data_text + ")"

                if len(echart_code) > 0 and str(echart_code).__contains__('x'):
                    is_chart = True
                    print("echart_name : ", echart_name)
                    # 格式化echart_code
                    # if base_util.is_json(str(echart_code)):
                    #     json_obj = json.loads(str(echart_code))
                    #     echart_code = json.dumps(json_obj)
                    re_str = await bi_proxy.run_echart_code(str(echart_code), echart_name)
                    # 添加日志，查看 bi_proxy.run_echart_code 的结果
                    print("bi_proxy.run_echart_code result: ", re_str)
                    logger.info("bi_proxy.run_echart_code result: " + str(re_str))
                    base_mess.append(re_str)

            error_times = 0
            for i in range(max_retry_times):
                try:
                    planner_user = self.agent_instance_util.get_agent_planner_user()
                    analyst = self.agent_instance_util.get_agent_analyst()

                    # 检查是否有空数据图表
                    has_empty_charts = False
                    for img_str in base_content:
                        echart_code = img_str.get('echart_code')
                        if echart_code and 'series' in echart_code:
                            has_data = False
                            for series in echart_code['series']:
                                if series.get('data') and len(series['data']) > 0:
                                    has_data = True
                                    break
                            if not has_data:
                                has_empty_charts = True
                                break

                    question_supplement = 'Please make an analysis and summary in English, including which charts were generated, and briefly introduce the contents of these charts.'
                    if has_empty_charts:
                        question_supplement += ' Note that some charts have no data. Please explain possible reasons why the data might be missing and suggest solutions.'
                    question_supplement += ' IMPORTANT: Do not add "TERMINATE" at the end of your message.'

                    if self.language_mode == language_chinese:
                        if is_chart:
                            question_supplement = ' 请用中文，简单介绍一下已生成图表中的数据内容.'
                            if has_empty_charts:
                                question_supplement += ' 注意：某些图表没有数据。请解释可能的原因并提出解决方案。'
                        else:
                            question_supplement = ' 请用中文，从上诉对话中分析总结出问题的答案.'
                        question_supplement += ' 重要提示：请不要在消息末尾添加"TERMINATE"。'
                    elif self.language_mode == CONFIG.language_japanese:
                        if is_chart:
                            question_supplement = ' 生成されたグラフのデータ内容について、簡単に日本語で説明してください。'
                            if has_empty_charts:
                                question_supplement += ' 注意：一部のグラフにデータがありません。考えられる理由を説明し、解決策を提案してください。'
                        else:
                            question_supplement = ' 上記の対話から問題の答えを分析し、日本語で要約してください。'
                        question_supplement += ' 重要：メッセージの最後に「TERMINATE」を追加しないでください。'

                    # 添加日志，查看发送给 Analyst 的消息内容
                    message_to_analyst = str(base_mess) + '\n' + self.question_ask + '\n' + question_supplement
                    print("Message to Analyst: ", message_to_analyst)
                    logger.info("Message to Analyst: " + message_to_analyst)

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

                        # 添加日志，查看从 Analyst 收到的消息内容
                        print("Message from Analyst: ", last_message)
                        logger.info("Message from Analyst: " + str(last_message))
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

