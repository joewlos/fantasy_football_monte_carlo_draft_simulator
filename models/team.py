# -*- coding: utf-8 -*-
"""
PYDANTIC MODELS FOR TEAMS
"""
from annotated_types import Len
from .config import DRAFT_YEAR, ROSTER_SIZE, ROUND_SIZE, SNAKE_DRAFT, STARTERS_SIZE
import copy
from .player import Player
from .position import PositionMaxPoints, PositionSizes, PositionTierDistributions
from pydantic import BaseModel, ConfigDict, model_validator
from sklearn.base import RegressorMixin
from typing import Annotated, List


# Load the position sizes, determined by environment variables
ps = PositionSizes()


"""
TEAM HELPER FUNCTION
"""


def fill_starters(roster):
    """
    Use projected points to fill the roster with the best players
    (used twice within the Team model, so it's a helper function)
    """
    not_flex = []
    output = {}

    # Perform the iteration for each position
    for position, size in ps.model_dump().items():
        players = [player for player in roster if player["position"] == position]
        if players:

            # Sort by projected points and take the top players
            output[position] = sorted(
                players,
                key=lambda x: x["points"][DRAFT_YEAR]["projected_points"],
                reverse=True,
            )[:size]

            # Add those players to the not_flex list
            not_flex.extend(output[position])

    # Take the best remaining RB, WR, or TE for flex
    flex_players = [
        player
        for player in roster
        if player["position"] in ["rb", "wr", "te"] and player not in not_flex
    ]
    output["flex"] = sorted(
        flex_players,
        key=lambda x: x["points"][DRAFT_YEAR]["projected_points"],
        reverse=True,
    )[: ps.flex]

    # Combine all positions for starters
    positions = ps.model_dump().keys() | {"flex"}
    output["starters"] = [
        player
        for position in positions
        if position in output
        for player in output[position]
    ]
    return output


"""
MODELS
"""


class Team(BaseModel):
    """
    A fantasy football team with a name, owner, and roster of players,
    which updates its starters with the best players when they are added
    to the roster
    """

    model_config = ConfigDict(
        validate_assignment=True
    )  # Enable validation on assignment, so that starters are updated

    # Team information, including whether or not this team is the "simulator's"
    name: str
    owner: str
    simulator: bool = False
    draft_order: int

    # Roster is a list of players, while starters are the best for a position
    roster: Annotated[List[Player], Len(max_length=ROSTER_SIZE)] = []
    starters: Annotated[List[Player], Len(max_length=STARTERS_SIZE)] = []

    # Starting positions
    qb: Annotated[List[Player], Len(max_length=ps.qb)] = []
    rb: Annotated[List[Player], Len(max_length=ps.rb)] = []
    wr: Annotated[List[Player], Len(max_length=ps.wr)] = []
    te: Annotated[List[Player], Len(max_length=ps.te)] = []
    flex: Annotated[List[Player], Len(max_length=ps.flex)] = []
    dst: Annotated[List[Player], Len(max_length=ps.dst)] = []
    k: Annotated[List[Player], Len(max_length=ps.k)] = []

    @model_validator(mode="before")
    def autofill_starters(cls, data):
        """
        Use the roster to autofill the positions for starters
        """
        if "roster" not in data or not data["roster"]:
            return data  # If roster is not in data, just return the data - there's nothing to do
        starters = fill_starters(data["roster"])
        for position, players in starters.items():
            data[position] = players
        data["starters"] = starters.get("starters", [])
        return data

    def draft_turn_position_weights(
        self, pick_number: int, model: RegressorMixin
    ) -> dict:
        """
        Use the starting line-up to determine the weight each
        position should have when randomly selecting a player
        """
        position_weights = {}
        probabilities = model.predict_proba([[pick_number]])[0]
        for i, position in enumerate(model.classes_):
            position_weights[position] = probabilities[i]

        # For each position, check if the starters are filled
        starting_positions = ["qb", "rb", "wr", "te", "dst", "k"]
        starting_filled = 0
        for position in starting_positions:
            if len(getattr(self, position)) == ps.model_dump()[position]:
                starting_filled += 1

        # If all of the important positions are filled, return the position weights
        if starting_filled == len(starting_positions):
            return position_weights

        # Otherwise, adjust the weights based on the number of important positions filled
        for position in starting_positions:
            if len(getattr(self, position)) == ps.model_dump()[position]:
                position_weights[position] = 0

        # Recalculate the total weight and return the position weights
        total_weight = sum(position_weights.values())
        return {
            position: weight / total_weight
            for position, weight in position_weights.items()
        }

    def projected_roster_points(self, year: int = DRAFT_YEAR) -> int:
        """
        Calculate the total projected points for the whole roster, not just the starters,
        using the draft year as the default year
        """
        return sum([player.points[year].projected_points for player in self.roster])

    def projected_starter_points(self, year: int = DRAFT_YEAR) -> int:
        """
        Calculate the total projected points for the starters only,
        using the draft year as the default year
        """
        return sum([player.points[year].projected_points for player in self.starters])

    def randomized_roster_points(
        self,
        distributions: PositionTierDistributions = PositionTierDistributions(),
        max_points: PositionMaxPoints = PositionMaxPoints(),
        year: int = DRAFT_YEAR,
    ) -> int:
        """
        Calculate the total randomized points for the whole roster, not just the starters,
        using the draft year as the default year
        """
        return sum(
            [
                player.randomized_points(
                    distributions=distributions, max_points=max_points, year=year
                ).randomized_points
                for player in self.roster
            ]
        )

    def randomized_starter_points(
        self,
        distributions: PositionTierDistributions = PositionTierDistributions(),
        max_points: PositionMaxPoints = PositionMaxPoints(),
        year: int = DRAFT_YEAR,
    ) -> int:
        """
        Calculate the total randomized points for the starters only,
        using the draft year as the default year
        """
        roster_copy = copy.deepcopy(self.roster)
        for player in roster_copy:
            player.points[year].projected_points = player.randomized_points(
                distributions=distributions, max_points=max_points, year=year
            ).randomized_points
        starters = fill_starters([x.model_dump() for x in roster_copy])["starters"]
        return sum([player["points"][year]["projected_points"] for player in starters])


class League(BaseModel):
    """
    All teams in the league, with draft order, based on settings
    """

    teams: List[Team]
    snake_draft: bool = SNAKE_DRAFT
    draft_order: List[int] = []
    draft_results: List[Team] = []
    current_draft_turn: int = 0

    @model_validator(mode="before")
    def sort_by_draft_order(cls, data):
        """
        Sort the teams into their draft order and then create a list of their indices
        to help populate the draft results
        """
        data["teams"] = sorted(data["teams"], key=lambda x: x.draft_order)

        # For the number of rounds, create the draft order as a list
        data["draft_order"] = []
        team_indices = [data["teams"].index(team) for team in data["teams"]]
        for i in range(ROUND_SIZE):
            if data["snake_draft"]:
                if i % 2 == 0:
                    data["draft_order"].extend(team_indices)
                else:
                    data["draft_order"].extend(team_indices[::-1])
            else:
                data["draft_order"].extend(team_indices)

        # Return the data to populate the model
        return data

    def rank_by_projected_team_points(self) -> list:
        """
        Return a sorted list of the teams by projected points
        """
        return sorted(
            self.teams, key=lambda x: x.projected_roster_points(), reverse=True
        )

    def add_player_to_current_draft_turn_team(self, player: Player) -> Team:
        """
        Draft a player and return the team that drafted the player
        """
        team_index = self.draft_order[0]
        team = self.teams[team_index]

        # Append the player to the team's roster
        team.roster.append(player)

        # Reinitialize team, appended to draft_results, with the new player on the roster
        team_dict = team.model_dump()
        self.teams[team_index] = Team(**team_dict)
        self.draft_results.append(Team(**team_dict))

        # Increment the current draft turn
        self.current_draft_turn += 1
        self.draft_order.pop(
            0
        )  # Update the order to reflect that the turn has been taken
        return
