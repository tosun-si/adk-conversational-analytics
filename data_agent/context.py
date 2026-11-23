"""Authored context of the CA data agent, as code.

This is the "semantic layer" of Conversational Analytics. The CA agent reads the
BigQuery schema (and its column descriptions) on its own, but accuracy comes
from what we author here:

1. Structured context on tables / columns: description, synonyms, tags.
2. Glossary terms: business vocabulary ("joueur décisif", "phase finale", ...).
3. Example queries: NL question → SQL pairs. CA reuses them as *verified
   queries* (the response's `matched_query` tells when one was used).
4. System instruction (YAML): persona + rules that have no structured field.
5. Options: guardrails such as the max bytes billed per BigQuery job.

Versioned in git, pushed by `provision.py` (`make data-agent`) → the data agent
is reproducible and reviewable like any other infra. Edits made in the console
are overwritten by the next `make data-agent`: this file is the source of truth.
"""

from pathlib import Path

from google.cloud import geminidataanalytics_v1 as ca

from data_agent.config import DATASET_ID, PROJECT_ID, fq

# 1 GB: the tables are tiny, anything bigger is a runaway query.
MAX_BILLED_BYTES = 1_000_000_000

# Column descriptions already live in BigQuery (data/schemas/ of the sibling
# repo) and CA reads them. Only the columns that need French vocabulary or a
# usage rule are authored here: (name, description, synonyms).
_PLAYER_FIELDS = [
    (
        "player_name",
        "Player name with accents as published by FIFA ('Kylian Mbappé'). Display it, never filter on it.",
        ["joueur", "player", "nom"],
    ),
    (
        "player_search_name",
        "Lower-case ASCII player name ('kylian mbappe'). Filter on it with LIKE '%<last name>%'.",
        ["recherche joueur"],
    ),
    (
        "team",
        "National team, English name ('France', 'Spain', 'Ivory Coast').",
        ["équipe", "sélection", "pays", "nation"],
    ),
    (
        "club",
        "Club at the time of the tournament ('Paris Saint-Germain', 'Real Madrid C. F.').",
        ["club", "équipe de club"],
    ),
    (
        "club_country",
        "3-letter code of the club's league country: FRA = Ligue 1, ENG = Premier League, ESP = LaLiga.",
        ["championnat", "ligue", "league"],
    ),
    (
        "team_stage_reached",
        "How far the player's national team went; 'Champion' = world champion.",
        ["parcours", "champion du monde", "élimination"],
    ),
    (
        "goals",
        "Goals scored, penalties included, own goals and shoot-outs excluded.",
        ["buts", "buteurs"],
    ),
    ("assists", "Assists (FBref).", ["passes décisives", "passeurs", "offrandes"]),
    ("minutes_played", "Total minutes played.", ["temps de jeu", "minutes"]),
    ("matches_started", "Matches started.", ["titularisations", "titulaire"]),
    (
        "matches_played",
        "Matches played (started or came on).",
        ["matchs joués", "sélections"],
    ),
    ("goals_per_90", "Goals per 90 minutes.", ["buts par 90", "efficacité"]),
    ("age_at_tournament", "Age on 2026-06-11.", ["âge", "jeune", "plus jeune"]),
    ("yellow_cards", "Yellow cards.", ["cartons jaunes"]),
    ("red_cards", "Red cards.", ["cartons rouges", "expulsions"]),
]

# (table, description, synonyms, authored fields)
_TABLES = [
    (
        "players",
        (
            "One row per player of the 2026 FIFA World Cup (USA, Canada, Mexico) with "
            "tournament-wide statistics: goals, assists, minutes, cards, club. "
            "First choice for any player question."
        ),
        ["joueurs", "players", "stats joueurs", "buteurs"],
        _PLAYER_FIELDS,
    ),
    (
        "teams",
        (
            "One row per national team (48): group, stage reached, final ranking, "
            "wins/draws/losses, goals for/against, clean sheets, cards."
        ),
        ["équipes", "sélections", "nations", "classement"],
        [("team", "National team, English name.", ["équipe", "sélection", "pays"])],
    ),
    (
        "team_matches",
        (
            "One row per team and per match (2 rows per match): goals for/against, "
            "result. Use it for any 'per team per match / per stage' question."
        ),
        ["matchs par équipe", "résultats", "parcours match par match"],
        [("team", "The team this row is about.", ["équipe", "sélection"])],
    ),
    (
        "player_matches",
        (
            "One row per player and per match played: goals, minutes, cards, started. "
            "Use it for 'match after match' questions about a player."
        ),
        ["match par match", "feuille de match", "stats par match"],
        [],
    ),
    (
        "matches",
        (
            "One row per match (104): stage, teams, score after 90 minutes and after "
            "extra time, penalty shoot-out, winner, venue, attendance, referee."
        ),
        ["matchs", "rencontres", "scores", "finale"],
        [],
    ),
]

# The business vocabulary (in the sibling repo these were prompts/business_rules.md).
# (term, definition, labels = the words users type)
_GLOSSARY = [
    (
        "Goal contributions",
        "goals + assists, from the players table.",
        ["joueur décisif", "contributions", "buts + passes", "le plus décisif"],
    ),
    (
        "Efficiency ranking",
        (
            "Rankings on goals_per_90 or minutes_per_goal only include players with "
            "minutes_played >= 180; otherwise a one-goal cameo tops the list. Say so."
        ),
        ["efficacité", "le plus efficace", "buts par 90", "ratio"],
    ),
    (
        "Knockout stage",
        "Matches with stage_order >= 2 (Round of 32 onwards).",
        ["phase finale", "phase à élimination directe", "matchs à élimination"],
    ),
    (
        "World champion",
        (
            "The champion team: teams.stage_reached = 'Champion' (players: "
            "team_stage_reached = 'Champion')."
        ),
        ["champion du monde", "vainqueur", "a gagné la Coupe du monde"],
    ),
    (
        "Ligue 1 player",
        "Player whose club plays in France: players.club_country = 'FRA'.",
        ["joueur de Ligue 1", "championnat de France"],
    ),
    (
        "PSG",
        "Paris Saint-Germain: players.club = 'Paris Saint-Germain'.",
        ["PSG", "Paris", "le club de la capitale"],
    ),
    (
        "Team style",
        (
            "OFFENSIVE if goals_for / matches_played >= 2.0, SOLID DEFENCE if "
            "goals_against / matches_played < 1.0, else BALANCED (teams table)."
        ),
        ["style de jeu", "équipe offensive", "meilleure défense"],
    ),
    (
        "Discipline points",
        "yellow_cards * 1 + red_cards * 3. Lower is cleaner.",
        ["fair-play", "discipline", "équipe la plus propre"],
    ),
    (
        "Penalty shoot-out",
        "Shoot-out kicks are never goals. A match won on penalties counts as a win.",
        ["tirs au but", "séance de penalties"],
    ),
]


def _table_reference(table, description, synonyms, fields) -> ca.BigQueryTableReference:
    return ca.BigQueryTableReference(
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        table_id=table,
        schema=ca.Schema(
            description=description,
            synonyms=synonyms,
            tags=["football", "world cup 2026"],
            fields=[ca.Field(name=n, description=d, synonyms=s) for n, d, s in fields],
        ),
    )


def _example_queries() -> list[ca.ExampleQuery]:
    players, team_matches, player_matches = (
        fq("players"),
        fq("team_matches"),
        fq("player_matches"),
    )
    return [
        ca.ExampleQuery(
            natural_language_question="Qui a marqué le plus de buts ?",
            sql_query=(
                f"SELECT player_name, team, goals FROM `{players}` "
                "ORDER BY goals DESC, minutes_played ASC LIMIT 5"
            ),
        ),
        ca.ExampleQuery(
            natural_language_question="Qui sont les 3 meilleurs buteurs de la France ?",
            sql_query=(
                f"SELECT player_name, goals FROM `{players}` WHERE team = 'France' "
                "ORDER BY goals DESC, minutes_played ASC LIMIT 3"
            ),
        ),
        ca.ExampleQuery(
            natural_language_question="Quels clubs ont fourni le plus de buts ?",
            sql_query=(
                f"SELECT club, SUM(goals) AS goals FROM `{players}` "
                "GROUP BY club ORDER BY goals DESC LIMIT 10"
            ),
        ),
        ca.ExampleQuery(
            natural_language_question="Quel joueur du PSG est champion du monde ?",
            sql_query=(
                f"SELECT player_name, team FROM `{players}` "
                "WHERE club = 'Paris Saint-Germain' AND team_stage_reached = 'Champion'"
            ),
        ),
        ca.ExampleQuery(
            natural_language_question="Le joueur du PSG le plus décisif",
            sql_query=(
                "SELECT player_name, team, goals, assists, goals + assists AS contributions "
                f"FROM `{players}` WHERE club = 'Paris Saint-Germain' "
                "ORDER BY contributions DESC, minutes_played ASC LIMIT 5"
            ),
        ),
        # Parameterized examples: CA binds {player} / {team} from the question.
        ca.ExampleQuery(
            natural_language_question="Profil complet de {player}",
            sql_query=(
                "SELECT player_name, team, club, position_label, age_at_tournament, "
                "matches_played, matches_started, minutes_played, goals, assists, "
                "goals_per_90, yellow_cards, red_cards "
                f"FROM `{players}` WHERE player_search_name LIKE CONCAT('%', LOWER(@player), '%')"
            ),
            parameters=[
                ca.QueryParameter(
                    name="player",
                    data_type="STRING",
                    description="Player last name, lower-case without accents, e.g. 'mbappe'.",
                )
            ],
        ),
        ca.ExampleQuery(
            natural_language_question="Buts de {player} match après match",
            sql_query=(
                "SELECT match_date, opponent, stage, goals "
                f"FROM `{player_matches}` WHERE player_search_name LIKE CONCAT('%', LOWER(@player), '%') "
                "ORDER BY match_date"
            ),
            parameters=[
                ca.QueryParameter(
                    name="player",
                    data_type="STRING",
                    description="Player last name, lower-case without accents, e.g. 'mbappe'.",
                )
            ],
        ),
        ca.ExampleQuery(
            natural_language_question="Buts par phase pour la France et l'Espagne",
            sql_query=(
                "SELECT team, stage, SUM(goals_for) AS goals "
                f"FROM `{team_matches}` WHERE team IN ('France', 'Spain') "
                "GROUP BY team, stage, stage_order ORDER BY team, stage_order"
            ),
        ),
    ]


def _system_instruction() -> str:
    yaml_text = (Path(__file__).parent / "system_instruction.yaml").read_text()
    return yaml_text.replace("{{DATASET}}", f"{PROJECT_ID}.{DATASET_ID}")


def build_context() -> ca.Context:
    context = ca.Context(
        system_instruction=_system_instruction(),
        datasource_references=ca.DatasourceReferences(
            bq=ca.BigQueryTableReferences(
                table_references=[_table_reference(*t) for t in _TABLES]
            )
        ),
        example_queries=_example_queries(),
        glossary_terms=[
            ca.GlossaryTerm(display_name=n, description=d, labels=labels)
            for n, d, labels in _GLOSSARY
        ],
    )
    context.options.datasource.big_query_max_billed_bytes = MAX_BILLED_BYTES
    return context
