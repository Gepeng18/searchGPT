import os
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import openai
import pandas as pd
import yaml

from Util import setup_logger, get_project_root, storage_cached
from website.sender import Sender, MSG_TYPE_SEARCH_STEP, MSG_TYPE_OPEN_AI_STREAM

logger = setup_logger('LLMService')


class LLMService(ABC):
    def __init__(self, config):
        self.config = config

    def clean_response_text(self, response_text: str):
        return response_text.replace("\n", "")

    def get_prompt(self, search_text: str, gpt_input_text_df: pd.DataFrame):
        logger.info(f"OpenAIService.get_prompt. search_text: {search_text}, gpt_input_text_df.shape: {gpt_input_text_df.shape}")
        prompt_length_limit = 3000  # obsolete
        is_use_source = self.config.get('source_service').get('is_use_source')
        if is_use_source:
            prompt_engineering = f"\n\nAnswer the question '{search_text}' using above information with about 100 words:"
            prompt = ""
            for index, row in gpt_input_text_df.iterrows():
                prompt += f"""{row['text']}\n"""
            # limit the prompt length
            prompt = prompt[:prompt_length_limit]
            return prompt + prompt_engineering
        else:
            return f"\n\nAnswer the question '{search_text}' with about 100 words:"

    def get_prompt_v2(self, search_text: str, gpt_input_text_df: pd.DataFrame):
        logger.info(f"OpenAIService.get_prompt_v2. search_text: {search_text}, gpt_input_text_df.shape: {gpt_input_text_df.shape}")
        context_str = ""
        gpt_input_text_df = gpt_input_text_df.sort_values('url_id')
        url_id_list = gpt_input_text_df['url_id'].unique()
        for url_id in url_id_list:
            context_str += f"Source ({url_id})\n"
            for index, row in gpt_input_text_df[gpt_input_text_df['url_id'] == url_id].iterrows():
                context_str += f"{row['text']}\n"
            context_str += "\n"
        prompt_length_limit = 3000 # obsolete
        context_str = context_str[:prompt_length_limit]
        prompt = \
            f"""
Answer with 100 words for the question below based on the provided sources using a scientific tone. 
If the context is insufficient, reply "I cannot answer".
Use Markdown for formatting code or text.
Source:
{context_str}
Question: {search_text}
Answer:
"""
        return prompt

    def get_prompt_v3(self, search_text: str, gpt_input_text_df: pd.DataFrame):
        language = self.config.get('general').get('language')
        if not self.config.get('source_service').get('is_use_source'):
            prompt = \
                f"""
Instructions: Write a comprehensive reply to the given query.  
If the context is insufficient, reply "I cannot answer".
Query: {search_text}
"""
            return prompt

        logger.info(f"OpenAIService.get_prompt_v3. search_text: {search_text}, gpt_input_text_df.shape: {gpt_input_text_df.shape}")
        context_str = ""
        for _, row_url in gpt_input_text_df[['url_id', 'url']].drop_duplicates().iterrows():
            domain = urlparse(row_url['url']).netloc.replace('www.', '')
            context_str += f"Source [{row_url['url_id']}] {domain}\n"
            for index, row in gpt_input_text_df[(gpt_input_text_df['url_id'] == row_url['url_id']) & gpt_input_text_df['in_scope']].iterrows():
                context_str += f"{row['text']}\n"
            context_str += "\n\n"
        prompt_length_limit = self.config.get('llm_service').get('openai_api').get('prompt').get('prompt_length_limit')
        context_str = context_str[:prompt_length_limit]
        prompt = \
            f"""
Web search result:
{context_str}

Instructions: Using the provided web search results, write a comprehensive reply to the given query. 
Make sure to cite results using [number] notation after the reference.
If the provided search results refer to multiple subjects with the same name, write separate answers for each subject.
Answer in language: {language}
If the context is insufficient, reply "I cannot answer because my reference sources don't have related info" in language {language}.
Query: {search_text}
"""
        return prompt

    @abstractmethod
    def call_api(self, prompt):
        pass


class OpenAIService(LLMService):
    def __init__(self, config, sender: Sender = None):
        super().__init__(config)
        self.sender = sender
        open_api_key = config.get('llm_service').get('openai_api').get('api_key')
        if open_api_key is None:
            raise Exception("OpenAI API key is not set.")
        os.environ["OPENAI_API_BASE"] = "https://api.xiaoai.plus/v1"
        os.environ["OPENAI_API_KEY"] = "sk-ZlUIfpKgpq13MKn7Ac3574A47cEb45A59b6a7b0e9bC3E84a"

    @storage_cached('openai', 'prompt')
    def call_api(self, prompt: str):
        if self.sender is not None:
            self.sender.send_message(msg_type=MSG_TYPE_SEARCH_STEP, msg='Calling OpenAI API ...')

        openai_api_config = self.config.get('llm_service').get('openai_api')
        model = openai_api_config.get('model')
        is_stream = openai_api_config.get('stream')
        logger.info(f"OpenAIService.call_api. model: {model}, len(prompt): {len(prompt)}")

        if model in ['gpt-3.5-turbo', 'gpt-4']:
            try:
                # response = openai.ChatCompletion.create(
                #     model=model,
                #     messages=[
                #         {"role": "system", "content": "You are a helpful search engine."},
                #         {"role": "user", "content": prompt}
                #     ],
                #     stream=is_stream
                # )
                from langchain_openai import OpenAIEmbeddings,ChatOpenAI
                from langchain.schema import HumanMessage, SystemMessage

                # 初始化 ChatOpenAI 模型
                llm = ChatOpenAI(model=model, streaming=is_stream)

                # 构造消息
                messages = [
                    SystemMessage(content="You are a helpful search engine."),
                    HumanMessage(content=prompt)
                ]

            except Exception as ex:
                raise ex

            from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
            # 定义流式响应处理逻辑
            class CustomStreamingCallback(StreamingStdOutCallbackHandler):
                def __init__(self, sender=None):
                    self.sender = sender
                    self.collected_messages = []

                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    # 处理新的 token
                    if self.sender is not None:
                        self.sender.send_message(msg_type=MSG_TYPE_OPEN_AI_STREAM, msg=token)
                    self.collected_messages.append(token)

                def get_full_reply(self):
                    return ''.join(self.collected_messages)

            # 创建自定义回调处理器
            custom_callback = CustomStreamingCallback(sender=self.sender)
            # 调用模型并传入回调处理器
            if is_stream:
                response = llm(messages, callbacks=[custom_callback])
                full_reply_content = custom_callback.get_full_reply()
                return full_reply_content
            else:
                response = llm(messages)
                return response.content
        else:
            try:
                response = openai.Completion.create(
                    model=model,
                    prompt=prompt,
                    max_tokens=openai_api_config.get('max_tokens'),
                    temperature=openai_api_config.get('temperature'),
                    top_p=openai_api_config.get('top_p'),
                )
            except Exception as ex:
                raise ex
            return self.clean_response_text(response.choices[0].text)


class GooseAIService(LLMService):
    def __init__(self, config, sender: Sender = None):
        super().__init__(config)
        self.sender = sender
        goose_api_key = config.get('goose_ai_api').get('api_key')
        if goose_api_key is None:
            raise Exception("Goose API key is not set.")
        openai.api_key = goose_api_key
        openai.api_base = config.get('goose_ai_api').get('api_base')

    @storage_cached('gooseai', 'prompt')
    def call_api(self, prompt: str, sender: Sender = None):
        if self.sender is not None:
            self.sender.send_message(msg_type=MSG_TYPE_SEARCH_STEP, msg='Calling gooseAI API ...')
        logger.info(f"GooseAIService.call_openai_api. len(prompt): {len(prompt)}")
        goose_api_config = self.config.get('goose_ai_api')
        try:
            response = openai.Completion.create(
                engine=goose_api_config.get('model'),
                prompt=prompt,
                max_tokens=goose_api_config.get('max_tokens'),
                # stream=True
            )
        except Exception as ex:
            raise ex
        return self.clean_response_text(response.choices[0].text)


class LLMServiceFactory:
    @staticmethod
    def create_llm_service(config, sender: Sender = None) -> LLMService:
        provider = config.get('llm_service').get('provider')
        if provider == 'openai':
            return OpenAIService(config, sender)
        elif provider == 'goose_ai':
            return GooseAIService(config, sender)
        else:
            logger.error(f'LLM Service for {provider} is not yet implemented.')
            raise NotImplementedError(f'LLM Service - {provider} - not is supported')


if __name__ == '__main__':
    # Load config
    with open(os.path.join(get_project_root(), 'src/config/config.yaml'), encoding='utf-8') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        service_factory = LLMServiceFactory()
        service = service_factory.create_llm_service(config)
        prompt = """
        """
        # response_text = service.call_openai_api('What is ChatGPT')
        response_text = service.call_api(prompt)
        print(response_text)
