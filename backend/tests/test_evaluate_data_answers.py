import uuid
from types import SimpleNamespace

from app.services.data_tool import DataConnectionInfo
from scripts import evaluate_data_answers as ev


def _result(answer, *, data=True, abstained=False):
    return SimpleNamespace(answer=answer, abstained=abstained, data=object() if data else None)


def test_a_data_answer_is_correct_with_one_full_set_of_numbers():
    question = ev.QUESTIONS[0]
    assert ev.correct(question, _result("Algarve 31 233,23, Lisboa 25 588,69, Norte 10 564,37, Alentejo 9 682,69 [D1]."))
    assert not ev.correct(question, _result("Algarve 31 233,23 e Lisboa 33 488,20 [D1]."))
    assert not ev.correct(question, _result("Algarve 31 233,23 [D1].", data=False))
    assert not ev.correct(question, _result("...", abstained=True))


def test_documents_and_no_answer_questions():
    documents = next(q for q in ev.QUESTIONS if q.source == "documents")
    assert ev.correct(documents, _result("Tens 25 dias uteis [1].", data=False))
    assert not ev.correct(documents, _result("25 [D1].", data=True))
    unanswerable = next(q for q in ev.QUESTIONS if q.source == "none")
    assert ev.correct(unanswerable, _result("Nao encontrei.", abstained=True))
    assert not ev.correct(unanswerable, _result("A margem foi 12% [D1]."))


def test_names_are_checked_for_the_top_customers():
    top = ev.QUESTIONS[2]
    assert ev.correct(top, _result("Cliente 018, Cliente 028 e Cliente 011 lideram [D1]."))
    assert not ev.correct(top, _result("Cliente 018 lidera [D1]."))


def test_the_data_tool_sees_only_the_demo_connection():
    class Inner:
        def connections(self):
            return [
                DataConnectionInfo(uuid.uuid4(), "ERP real", {}),
                DataConnectionInfo(uuid.uuid4(), ev.NAME, {}),
            ]

    assert [c.name for c in ev.DemoOnly(Inner()).connections()] == [ev.NAME]
