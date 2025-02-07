from SearchGPTService import SearchGPTService

if __name__ == '__main__':
    search_text = '搜索一个vmware 的激活码'

    search_gpt_service = SearchGPTService()
    response_text, source_text, data_json = search_gpt_service.query_and_get_answer(search_text=search_text)
    print()

