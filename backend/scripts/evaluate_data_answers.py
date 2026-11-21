"""Ask the agent fixed questions about the demo sales database (AL-4f).

Development only, and only on the invented data of infrastructure/demo-db:
it prints what the product never logs (each query the model wrote, the
database's error, the rows read, the refused draft and the model's raw
replies), so the data tool's prompts can be measured before they change.

The questions run through the real agent (answer_question) as the
organization's owner, with the configured model and the data gateway; the
data tool sees only the connection "Vendas (exemplo)". Nothing is written:
no history, no dashboard counts, no audit.

Run from the backend folder, in the container, with the app running:
    docker compose -f ../infrastructure/dev/docker-compose.yml run --rm backend python -m scripts.evaluate_data_answers
    ... --organization "Name or slug"   when there is more than one
    ... --only 1,3                       some questions only
"""

import argparse
import sys
import time
from dataclasses import dataclass, field

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.context import set_identity_context, set_organization_context
from app.services import answer_service
from app.services.answer_service import AgentLimits, answer_question, numbers_in
from app.services.data_tool import DataToolError, GatewayDataTool
from app.services.llm import get_chat_model
from scripts.create_demo_connection import NAME, OWNERS_SQL, check_target, choose


GATEWAY = "http://data-gateway:8100"


@dataclass
class Question:
    text: str
    # Any one of these sets of numbers (or names) must all be in the answer.
    expected: list[set[str]] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    # "data": from the database; "documents": not from it; "none": no answer.
    source: str = "data"


QUESTIONS = [
    Question(
        "Quanto fatur\u00e1mos por regi\u00e3o em outubro?",
        expected=[
            {"31233.23", "25588.69", "10564.37", "9682.69"},  # without cancelled
            {"35696.12", "33488.20", "10672.30", "10564.37"},  # all invoices
        ],
    ),
    Question("Quantas faturas est\u00e3o pendentes?", expected=[{"55"}]),
    Question(
        "Quais s\u00e3o os 5 clientes com mais fatura\u00e7\u00e3o?",
        names=["Cliente 018", "Cliente 028", "Cliente 011"],
    ),
    Question("Quantos clientes particulares temos no Algarve?", expected=[{"2"}]),
    Question("Quanto fatur\u00e1mos em setembro?", expected=[{"91602.65"}, {"97211.08"}]),
    Question("Quantas faturas foram anuladas em novembro?", expected=[{"2"}]),
    Question("Quantos dias de f\u00e9rias tenho por ano?", source="documents"),
    Question("Qual foi a margem de lucro em outubro?", source="none"),
]


class DemoOnly:
    """The data tool on the demo connection only, recording what it ran."""

    def __init__(self, inner: GatewayDataTool):
        self.inner = inner
        self.log: list[str] = []

    def connections(self):
        return [c for c in self.inner.connections() if c.name == NAME]

    def query(self, connection_id, sql):
        self.log.append(f"SQL:\n{sql}")
        try:
            result = self.inner.query(connection_id, sql)
        except DataToolError as exc:
            self.log.append(f"refused ({exc.sqlstate}): {exc.database_message or exc}")
            raise
        rows = "\n".join(" | ".join(str(v) for v in row) for row in result.rows[:10])
        self.log.append(f"{len(result.rows)} rows: {' | '.join(result.columns)}\n{rows}")
        return result


class Recording:
    """The configured model, recording each reply's kind and text."""

    def __init__(self, inner):
        self.inner = inner
        self.model = getattr(inner, "model", "model")
        self.replies: list[str] = []

    def complete(self, system, user, *, max_tokens):
        completion = self.inner.complete(system, user, max_tokens=max_tokens)
        kind = (
            "route" if "DATA or DOCUMENTS" in system
            else "relevance" if "<answer>" in user
            else "fix" if "<error>" in user
            else "query" if "<database" in user
            else "data answer" if "<data " in user
            else "documents answer"
        )
        self.replies.append(f"[{kind}] {completion.text.strip()}")
        return completion


def correct(question: Question, result) -> bool:
    if question.source == "none":
        return result.abstained
    if result.abstained:
        return False
    if question.source == "documents":
        return result.data is None
    if result.data is None:
        return False
    found = numbers_in(result.answer)
    if question.expected and not any(
        {n.replace(".", "") for n in variant} <= found for variant in question.expected
    ):
        return False
    return all(name in result.answer for name in question.names)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--organization")
    parser.add_argument("--only", help="question numbers, for example 1,3")
    arguments = parser.parse_args()

    problem = check_target(settings.MIGRATION_DATABASE_URL)
    if problem:
        print(f"PAROU: {problem}.")
        return 1
    settings.DATA_GATEWAY_URL = settings.DATA_GATEWAY_URL or GATEWAY
    if not settings.DATA_GATEWAY_TOKEN:
        print("PAROU: DATA_GATEWAY_TOKEN is not set.")
        return 1
    chosen = range(1, len(QUESTIONS) + 1)
    if arguments.only:
        chosen = [int(n) for n in arguments.only.split(",")]

    model = Recording(get_chat_model())
    answer_service.get_chat_model = lambda: model

    engine = create_engine(settings.MIGRATION_DATABASE_URL)
    score, wrong, times = 0, 0, []
    try:
        with Session(engine) as db:
            organization, problem = choose(db.execute(text(OWNERS_SQL)).all(), arguments.organization)
            if problem:
                print(f"PAROU: {problem}.")
                return 1
            db.execute(text("SET LOCAL ROLE eka_runtime"))
            set_identity_context(
                db, issuer=organization.issuer, subject=organization.subject, user_id=organization.user_id
            )
            set_organization_context(db, organization_id=organization.id)
            tool = DemoOnly(GatewayDataTool(organization_id=organization.id, role="owner"))
            if not tool.connections():
                print(f"PAROU: no active connection {NAME!r} with a catalog in {organization.name!r}.")
                return 1

            print(f"Organization {organization.name!r}, model {model.model}\n")
            for number in chosen:
                question = QUESTIONS[number - 1]
                tool.log.clear()
                model.replies.clear()
                started = time.perf_counter()
                result = answer_question(
                    db,
                    organization_id=organization.id,
                    question=question.text,
                    limits=AgentLimits(),
                    data_tool=tool,
                )
                times.append(time.perf_counter() - started)
                ok = correct(question, result)
                score += ok
                # The worst outcome: an answer shown that is not right.
                wrong += not ok and not result.abstained
                print("=" * 72)
                print(f"{number}. {question.text}   [{'OK' if ok else 'FALHOU'}]")
                print(f"data={result.data_outcome} steps={result.steps} tools={result.tool_calls} "
                      f"abstained={result.abstained} issues={result.issues} {times[-1]:.1f} s")
                for line in tool.log + model.replies:
                    print("  " + line.replace("\n", "\n  "))
                print(f"  ANSWER: {result.answer}")
                if result.draft:
                    print(f"  REFUSED DRAFT: {result.draft}")
                db.rollback()
                db.execute(text("SET LOCAL ROLE eka_runtime"))
    finally:
        engine.dispose()
    print("=" * 72)
    print(
        f"{score} of {len(chosen)} correct, {wrong} wrong answers shown, "
        f"{sum(times) / max(len(times), 1):.1f} s per question"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
