from SearchGPTService import SearchGPTService

if __name__ == '__main__':
    search_text = 'the source of dark energy'
    search_gpt_service = SearchGPTService()
    response_text, response_text_with_footnote, source_text = search_gpt_service.query_and_get_answer(search_text)
    # search_gpt_service.search_docs_and_get_answer(search_text, "<folder absolute path>")
