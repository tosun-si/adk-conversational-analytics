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
# usage rule are authored here.
_PLAYER_FIELDS = [
    ca.Field(
        name="player_name",
        description="Player name with accents as published by FIFA ('Kylian Mbappé'). Display it, never filter on it.",
        synonyms=["joueur", "player", "nom"],
    ),
    ca.Field(
        name="player_search_name",
        description="Lower-case ASCII player name ('kylian mbappe'). Filter on it with LIKE '%<last name>%'.",
        synonyms=["recherche joueur"],
    ),
    ca.Field(
        name="team",
        description="National team, English name ('France', 'Spain', 'Ivory Coast').",
        synonyms=["équipe", "sélection", "pays", "nation"],
    ),
    ca.Field(
        name="club",
        description="Club at the time of the tournament ('Paris Saint-Germain', 'Real Madrid C. F.').",
        synonyms=["club", "équipe de club"],
    ),
    ca.Field(
        name="club_country",
        description="3-letter code of the club's league country: FRA = Ligue 1, ENG = Premier League, ESP = LaLiga.",
        synonyms=["championnat", "ligue", "league"],
    ),
    ca.Field(
        name="team_stage_reached",
        description="How far the player's national team went; 'Champion' = world champion.",
        synonyms=["parcours", "champion du monde", "élimination"],
    ),
    ca.Field(
        name="goals",
        description="Goals scored, penalties included, own goals and shoot-outs excluded.",
        synonyms=["buts", "buteurs"],
    ),
    ca.Field(
        name="assists",
        description="Assists (FBref).",
        synonyms=["passes décisives", "passeurs", "offrandes"],
    ),
    ca.Field(
        name="minutes_played",
        description="Total minutes played.",
        synonyms=["temps de jeu", "minutes"],
    ),
    ca.Field(
        name="matches_started",
        description="Matches started.",
        synonyms=["titularisations", "titulaire"],
    ),
    ca.Field(
        name="matches_played",
        description="Matches played (started or came on).",
        synonyms=["matchs joués", "sélections"],
    ),
    ca.Field(
        name="goals_per_90",
        description="Goals per 90 minutes.",
        synonyms=["buts par 90", "efficacité"],
    ),
    ca.Field(
        name="age_at_tournament",
        description="Age on 2026-06-11.",
        synonyms=["âge", "jeune", "plus jeune"],
    ),
    ca.Field(
        name="yellow_cards", description="Yellow cards.", synonyms=["cartons jaunes"]
    ),
    ca.Field(
        name="red_cards",
        description="Red cards.",
        synonyms=["cartons rouges", "expulsions"],
    ),
]


def _table(
    *,
    table_id: str,
    description: str,
    synonyms: list[str],
    fields: list[ca.Field] | None = None,
) -> ca.BigQueryTableReference:
    return ca.BigQueryTableReference(
        project_id=PROJECT_ID,
        dataset_id=DATASET_ID,
        table_id=table_id,
        schema=ca.Schema(
            description=description,
            synonyms=synonyms,
            tags=["football", "world cup 2026"],
            fields=fields or [],
        ),
    )


# `synonyms` = other names of the table itself, never a hint about what it holds
# (that goes in the description or a glossary term).
_TABLES = [
    _table(
        table_id="players",
        description=(
            "One row per player of the 2026 FIFA World Cup (USA, Canada, Mexico) with "
            "tournament-wide statistics: goals, assists, minutes, cards, club. "
            "First choice for any player question."
        ),
        synonyms=["joueurs", "players", "stats joueurs", "buteurs"],
        fields=_PLAYER_FIELDS,
    ),
    _table(
        table_id="teams",
        description=(
            "One row per national team (48): group, stage reached, final ranking, "
            "wins/draws/losses, goals for/against, clean sheets, cards."
        ),
        synonyms=["équipes", "sélections", "nations"],
        fields=[
            ca.Field(
                name="team",
                description="National team, English name.",
                synonyms=["équipe", "sélection", "pays"],
            ),
            ca.Field(
                name="final_rank_bucket",
                description=(
                    "Final ranking in the tournament: 1 champion, 2 runner-up, 3 third, "
                    "4 fourth, then the best possible rank of the round where the team "
                    "went out (5 quarter-finals, 9 round of 16, 17 round of 32, 33 "
                    "group stage). Teams eliminated in the same round share it."
                ),
                synonyms=["classement final", "rang final"],
            ),
        ],
    ),
    _table(
        table_id="team_matches",
        description=(
            "One row per team and per match (2 rows per match): goals for/against, "
            "result. Use it for any 'per team per match / per stage' question."
        ),
        synonyms=["matchs par équipe", "résultats", "parcours match par match"],
        fields=[
            ca.Field(
                name="team",
                description="The team this row is about.",
                synonyms=["équipe", "sélection"],
            )
        ],
    ),
    _table(
        table_id="player_matches",
        description=(
            "One row per player and per match played: goals, minutes, cards, started. "
            "Use it for 'match after match' questions about a player."
        ),
        synonyms=["match par match", "feuille de match", "stats par match"],
    ),
    _table(
        table_id="matches",
        description=(
            "One row per match (104): stage, teams, score after 90 minutes and after "
            "extra time, penalty shoot-out, winner, venue, attendance, referee."
        ),
        synonyms=["matchs", "rencontres", "scores", "finale"],
    ),
]

# The business vocabulary (in the sibling repo these were prompts/business_rules.md).
# `labels` = the words users type.
_GLOSSARY = [
    ca.GlossaryTerm(
        display_name="Goal contributions",
        description="goals + assists, from the players table.",
        labels=["joueur décisif", "contributions", "buts + passes", "le plus décisif"],
    ),
    ca.GlossaryTerm(
        display_name="Efficiency ranking",
        description=(
            "Rankings on goals_per_90 or minutes_per_goal only include players with "
            "minutes_played >= 180; otherwise a one-goal cameo tops the list. Say so."
        ),
        labels=["efficacité", "le plus efficace", "buts par 90", "ratio"],
    ),
    ca.GlossaryTerm(
        display_name="Final ranking",
        description=(
            "The final ranking of the TEAMS in the tournament: teams.final_rank_bucket "
            "ascending (1 = champion), stage_reached as the label; teams eliminated in "
            "the same round are tied. Not a player ranking: 'classement des buteurs / "
            "passeurs' is a ranking of players on players.goals / players.assists."
        ),
        labels=[
            "classement",
            "classement final",
            "classement des équipes",
            "rang final",
        ],
    ),
    ca.GlossaryTerm(
        display_name="Knockout stage",
        description="Matches with stage_order >= 2 (Round of 32 onwards).",
        labels=["phase finale", "phase à élimination directe", "matchs à élimination"],
    ),
    ca.GlossaryTerm(
        display_name="World champion",
        description=(
            "The champion team: teams.stage_reached = 'Champion' (players: "
            "team_stage_reached = 'Champion')."
        ),
        labels=["champion du monde", "vainqueur", "a gagné la Coupe du monde"],
    ),
    ca.GlossaryTerm(
        display_name="Ligue 1 player",
        description="Player whose club plays in France: players.club_country = 'FRA'.",
        labels=["joueur de Ligue 1", "championnat de France"],
    ),
    ca.GlossaryTerm(
        display_name="PSG",
        description="Paris Saint-Germain: players.club = 'Paris Saint-Germain'.",
        labels=["PSG", "Paris", "le club de la capitale"],
    ),
    ca.GlossaryTerm(
        display_name="Team style",
        description=(
            "OFFENSIVE if goals_for / matches_played >= 2.0, SOLID DEFENCE if "
            "goals_against / matches_played < 1.0, else BALANCED (teams table)."
        ),
        labels=["style de jeu", "équipe offensive", "meilleure défense"],
    ),
    ca.GlossaryTerm(
        display_name="Discipline points",
        description="yellow_cards * 1 + red_cards * 3. Lower is cleaner.",
        labels=["fair-play", "discipline", "équipe la plus propre"],
    ),
    ca.GlossaryTerm(
        display_name="Penalty shoot-out",
        description="Shoot-out kicks are never goals. A match won on penalties counts as a win.",
        labels=["tirs au but", "séance de penalties"],
    ),
]


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
            bq=ca.BigQueryTableReferences(table_references=_TABLES)
        ),
        example_queries=_example_queries(),
        glossary_terms=_GLOSSARY,
    )
    context.options.datasource.big_query_max_billed_bytes = MAX_BILLED_BYTES
    return context
