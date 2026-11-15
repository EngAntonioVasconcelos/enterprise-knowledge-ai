"""A larger library for the retrieval evaluation (AI-2b).

The 17 documents of the dataset make search look better than it is: the
reranker read 20 of 38 passages, more than half of the library. Real
companies have thousands of passages, many of them sharing words with the
question without answering it ("ferias" in the summer camp for employees'
children, "forklift" in the maintenance contract).

distractor_documents() builds such documents deterministically (same seed,
same text): about 20 subjects in Portuguese and English, each repeated for
several sites, departments and years, with sentences that reuse the
vocabulary of the questions but never their answers. They are readable by
everyone, so permissions are unchanged.
"""

import random


SITES = [
    "Lisboa", "Porto", "Braga", "Faro", "Coimbra", "Aveiro", "Leiria",
    "Setubal", "Viseu", "Evora",
]
TEAMS = ["Vendas", "Armazem", "Financeiro", "Frota", "Clientes", "Compras", "TI", "Marketing"]
TEAMS_EN = ["Sales", "Warehouse", "Finance", "Fleet", "Customer Care", "Purchasing", "IT", "Marketing"]
YEARS = [2023, 2024, 2025, 2026]

# (language, title, [(heading, [sentences])]). Placeholders: {site}, {team},
# {year}, {n}, {m}, {d}, {p}.
SUBJECTS = [
    ("pt", "Campo de F\u00e9rias para Filhos dos Colaboradores {year} - {site}", [
        ("Inscri\u00e7\u00f5es", [
            "O campo de f\u00e9rias de ver\u00e3o recebe filhos dos colaboradores entre os {n} e os 14 anos.",
            "As inscri\u00e7\u00f5es abrem em {d} de maio e a semana custa {m} euros por crian\u00e7a.",
        ]),
        ("Atividades", [
            "Durante os dias de campo h\u00e1 desporto, oficinas de ci\u00eancia e visitas ao armaz\u00e9m de {site}.",
            "O transporte \u00e9 feito em autocarro alugado e o almo\u00e7o \u00e9 servido no refeit\u00f3rio.",
        ]),
        ("Cancelamentos", [
            "Um cancelamento com menos de {d} dias de anteced\u00eancia n\u00e3o \u00e9 reembolsado.",
        ]),
    ]),
    ("en", "Forklift Maintenance Contract - {site} Depot", [
        ("Scope", [
            "The supplier services every forklift in the {site} depot every {n} weeks.",
            "Batteries are replaced when their capacity drops below {p} percent.",
        ]),
        ("Response times", [
            "A broken forklift is repaired within {d} business days; a spare unit is provided after {n} days.",
            "The contract value is {m} euros per year and is reviewed in {year}.",
        ]),
        ("Reporting", [
            "Maintenance visits are recorded in the facilities log, not in the safety incident form.",
        ]),
    ]),
    ("en", "Travel Insurance for Client Visits {year}", [
        ("Coverage", [
            "Clients visiting our sites are covered by a group travel policy up to {m} euros.",
            "The policy covers lost luggage and medical assistance during the visit.",
        ]),
        ("Claims", [
            "Insurance claims are sent to the broker within {d} days, with the incident report attached.",
            "Hotel costs for clients are booked by the {team_en} team and invoiced to the client.",
        ]),
    ]),
    ("pt", "Gestor de Palavras-passe: Implementa\u00e7\u00e3o na Equipa de {team}", [
        ("Calend\u00e1rio", [
            "O gestor de palavras-passe chega \u00e0 equipa de {team} na semana {n} de {year}.",
            "Cada pessoa importa as credenciais antigas e apaga as notas em papel.",
        ]),
        ("Forma\u00e7\u00e3o", [
            "Uma sess\u00e3o de forma\u00e7\u00e3o de {n} minutos explica a extens\u00e3o do navegador.",
            "As d\u00favidas s\u00e3o enviadas ao suporte de TI pelo portal interno.",
        ]),
    ]),
    ("en", "Laptop Purchase Procedure", [
        ("Requests", [
            "New laptops are requested by the manager of the {team_en} team through the IT portal.",
            "Standard models cost about {m} euros and are delivered within {d} working days.",
        ]),
        ("Replacement", [
            "Laptops are replaced every {n} years or earlier if repair costs exceed {p} percent of the price.",
            "Old laptops are wiped and donated to schools near the {site} office.",
        ]),
    ]),
    ("pt", "Semana do Bem-Estar {year} - {site}", [
        ("Programa", [
            "A semana do bem-estar inclui rastreios gratuitos, aulas de alongamento e palestras sobre sono.",
            "As consultas de nutri\u00e7\u00e3o t\u00eam {n} vagas por dia e s\u00e3o marcadas no portal.",
        ]),
        ("Parceiros", [
            "O seguro de sa\u00fade parceiro oferece um vale de {m} euros para \u00f3culos durante a semana.",
            "Os resultados dos rastreios s\u00e3o confidenciais e entregues apenas ao colaborador.",
        ]),
    ]),
    ("en", "Customer Gift Card Programme", [
        ("Issuing", [
            "Customer Care may issue gift cards of up to {m} euros to compensate a late delivery.",
            "Each gift card has a code and expires after {n} months.",
        ]),
        ("Limits", [
            "A customer can receive at most {d} gift cards per year.",
            "Gift cards are not given to suppliers or employees.",
        ]),
    ]),
    ("en", "Supplier Returns of Defective Parts - {site}", [
        ("When to return", [
            "Defective parts are returned to the supplier within {d} days of receipt.",
            "The warehouse in {site} keeps returned parts in a separate rack bay until collection.",
        ]),
        ("Credit notes", [
            "The supplier issues a credit note within {n} weeks; Finance checks it against the order.",
        ]),
    ]),
    ("pt", "Concurso para Compra de Cami\u00f5es {year}", [
        ("Objetivo", [
            "O concurso de {year} compra {n} cami\u00f5es novos para a frota do centro de {site}.",
            "As propostas s\u00e3o avaliadas pelo consumo, pre\u00e7o e servi\u00e7o p\u00f3s-venda.",
        ]),
        ("Prazos", [
            "As propostas s\u00e3o entregues at\u00e9 {d} de setembro e o j\u00fari decide em {n} semanas.",
            "O valor total previsto \u00e9 de {m} mil euros, aprovado pela administra\u00e7\u00e3o.",
        ]),
    ]),
    ("pt", "Reserva de Salas de Forma\u00e7\u00e3o - {site}", [
        ("Como reservar", [
            "As salas de forma\u00e7\u00e3o do piso {n} s\u00e3o reservadas no portal com {d} dias de anteced\u00eancia.",
            "Cada sala tem projetor, quadro branco e lugar para {m} pessoas.",
        ]),
        ("Regras", [
            "A sala \u00e9 libertada se ningu\u00e9m chegar nos primeiros 15 minutos.",
        ]),
    ]),
    ("en", "Remote Desktop Software Guide", [
        ("Installing", [
            "The remote desktop client is installed from the software centre on company laptops.",
            "It connects to office computers in {site} through the VPN.",
        ]),
        ("Sessions", [
            "Sessions close after {n} minutes without activity; files are never copied to home computers.",
            "Problems are reported to the IT desk with the computer name and a screenshot.",
        ]),
    ]),
    ("pt", "Parque de Estacionamento - {site}", [
        ("Lugares", [
            "O parque de {site} tem {m} lugares, dos quais {n} reservados a carros el\u00e9tricos.",
            "O cart\u00e3o de acesso abre a barreira entre as 7h e as 21h.",
        ]),
        ("Visitantes", [
            "Os visitantes estacionam nos lugares marcados junto \u00e0 rece\u00e7\u00e3o durante no m\u00e1ximo {d} horas.",
        ]),
    ]),
    ("en", "Quarterly Sales Report {year} - {team_en}", [
        ("Results", [
            "The {team_en} team closed the quarter with revenue of {m} thousand euros.",
            "Returns of goods fell to {p} percent of orders, the lowest value since {year}.",
        ]),
        ("Next quarter", [
            "Priorities are faster delivery in {site} and {n} new key accounts.",
        ]),
    ]),
    ("pt", "Plano de Sustentabilidade {year}", [
        ("Energia", [
            "Os armaz\u00e9ns de {site} instalam pain\u00e9is solares que cobrem {p} por cento do consumo.",
            "A ilumina\u00e7\u00e3o passa a LED e desliga-se nos corredores sem movimento.",
        ]),
        ("Frota", [
            "At\u00e9 {year} a frota ligeira ser\u00e1 el\u00e9trica e os cami\u00f5es testam biodiesel.",
            "Cada viagem de cami\u00e3o vazia \u00e9 registada para reduzir quil\u00f3metros sem carga.",
        ]),
    ]),
    ("en", "Office Cafeteria Rules - {site}", [
        ("Opening hours", [
            "The cafeteria in {site} opens from 8:00 to 16:00; lunch is served from 12:00.",
            "A meal costs {n} euros with the employee card.",
        ]),
        ("Allergies", [
            "Menus list the allergens of each dish; special meals are ordered {d} days ahead.",
        ]),
    ]),
    ("pt", "Procedimento de Visitas de Clientes - {team}", [
        ("Antes da visita", [
            "A equipa de {team} avisa a rece\u00e7\u00e3o com {d} dias de anteced\u00eancia e indica o n\u00famero de visitantes.",
            "Os visitantes recebem um cart\u00e3o tempor\u00e1rio e coletes de alta visibilidade no armaz\u00e9m.",
        ]),
        ("Durante a visita", [
            "Os visitantes est\u00e3o sempre acompanhados e n\u00e3o entram nas zonas de carga.",
            "Fotografias s\u00f3 com autoriza\u00e7\u00e3o do respons\u00e1vel do centro de {site}.",
        ]),
    ]),
    ("en", "Internal Mobility Programme", [
        ("Applying", [
            "Employees with at least {n} months in their role may apply to open positions.",
            "Applications are sent to Human Resources and the current manager is informed.",
        ]),
        ("Moving", [
            "The new team covers relocation costs up to {m} euros when the move is to {site}.",
        ]),
    ]),
    ("pt", "Manual do Sistema de Gest\u00e3o de Armaz\u00e9m", [
        ("Rece\u00e7\u00e3o", [
            "Cada palete recebida \u00e9 lida com o terminal port\u00e1til e arrumada na estante indicada.",
            "O sistema sugere a posi\u00e7\u00e3o com base no peso e na rota\u00e7\u00e3o do artigo.",
        ]),
        ("Invent\u00e1rio", [
            "O invent\u00e1rio rotativo conta {n} posi\u00e7\u00f5es por dia em {site}.",
            "Diferen\u00e7as acima de {p} por cento s\u00e3o analisadas pelo chefe de turno.",
        ]),
    ]),
    ("en", "Data Protection Notice for Employees", [
        ("What we keep", [
            "The company keeps contact details, contracts and training records of each employee.",
            "Records are kept for {n} years after the end of the contract.",
        ]),
        ("Your rights", [
            "Requests to see or correct personal data are answered within {d} days by the data protection officer.",
        ]),
    ]),
    ("pt", "Regulamento do Pr\u00e9mio de Desempenho {year}", [
        ("Crit\u00e9rios", [
            "O pr\u00e9mio de {year} depende dos objetivos da equipa de {team} e da avalia\u00e7\u00e3o individual.",
            "O valor m\u00e1ximo corresponde a {p} por cento da remunera\u00e7\u00e3o anual.",
        ]),
        ("Pagamento", [
            "O pr\u00e9mio \u00e9 pago em mar\u00e7o, juntamente com o vencimento.",
        ]),
    ]),
]

FILLER_PT = [
    "Este documento \u00e9 revisto anualmente pela dire\u00e7\u00e3o respons\u00e1vel.",
    "As d\u00favidas podem ser colocadas ao respons\u00e1vel da equipa de {team}.",
    "A vers\u00e3o em vigor est\u00e1 sempre dispon\u00edvel no portal interno.",
    "Casos n\u00e3o previstos s\u00e3o decididos pela administra\u00e7\u00e3o.",
]
FILLER_EN = [
    "This document is reviewed every year by its owner.",
    "Questions can be sent to the {team_en} team lead.",
    "The current version is always available on the intranet.",
    "Cases not covered here are decided by management.",
]


def distractor_documents(count: int = 400, seed: int = 7) -> dict[str, dict]:
    """count readable documents that share vocabulary with the questions."""
    rng = random.Random(seed)
    documents = {}
    for index in range(count):
        language, title, sections = SUBJECTS[index % len(SUBJECTS)]
        team = rng.randrange(len(TEAMS))
        values = {
            "site": rng.choice(SITES),
            "team": TEAMS[team],
            "team_en": TEAMS_EN[team],
            "year": rng.choice(YEARS),
            "n": rng.randint(2, 12),
            "m": rng.choice([80, 150, 250, 400, 900, 1500, 3200]),
            "d": rng.randint(3, 28),
            "p": rng.choice([15, 25, 35, 60, 70]),
        }
        filler = FILLER_PT if language == "pt" else FILLER_EN
        parts = []
        for number, (heading, sentences) in enumerate(sections, start=1):
            body = list(sentences) + rng.sample(filler, 2)
            parts.append(f"{number}. {heading}\n\n" + " ".join(body))
        text = "\n\n".join(parts).format(**values)
        documents[f"distractor-{index:03d}"] = {
            "title": title.format(**values) + f" ({index + 1})",
            "lang": language,
            "restricted": False,
            "text": text + "\n",
        }
    return documents


def with_distractors(dataset: dict, count: int = 400) -> dict:
    """The dataset with the distractor documents added to its library."""
    documents = dict(dataset["documents"])
    documents.update(distractor_documents(count))
    return {**dataset, "documents": documents}
