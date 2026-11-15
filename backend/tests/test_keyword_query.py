from app.services.search_service import keyword_query


def test_ordinary_questions_become_an_or_of_meaningful_words():
    assert keyword_query("Quantos dias de f\u00e9rias tenho?") == "dias or ferias"
    assert keyword_query("how many vacation days do I get") == "many or vacation or days"


def test_codes_stay_whole_and_words_are_not_repeated():
    assert keyword_query("formul\u00e1rio RH-12 e rh-12") == "formulario or rh-12"
    assert keyword_query("vers\u00e3o 2.5 do manual") == "versao or 2.5 or manual"


def test_a_question_of_only_stopwords_still_searches_something():
    assert keyword_query("de a o") == "de or a or o"


def test_advanced_syntax_is_left_to_the_user():
    for query in ('"dias de f\u00e9rias"', "f\u00e9rias -2023", "f\u00e9rias or licen\u00e7a"):
        assert keyword_query(query) == query
