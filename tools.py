"""NBA data tools — called by the agent to retrieve facts.

Each tool returns a JSON string. The agent parses these strings to build
the daily report.
"""

import json
import os
from dotenv import load_dotenv
from nba_api.stats.endpoints import (
    leaguedashteamstats,
    leaguedashplayerstats,
    teamgamelog,
    commonteamroster,
    leaguestandings,
    commonplayoffseries,
)
from langchain_tavily import TavilySearch
from config import CURRENT_SEASON, get_team_info

load_dotenv()


def get_team_status(team_abbreviation: str) -> str:
    """Returns team status: regular season, playoffs, or offseason, plus
    conference rank, division, and record. Called first per the prompt's
    team status gate.
    """
    team_info = get_team_info(team_abbreviation)
    if not team_info:
        return json.dumps({"error": f"Team '{team_abbreviation}' not found."})
    team_id = team_info['id']

    standings = leaguestandings.LeagueStandings(season=CURRENT_SEASON)
    st_df = standings.get_data_frames()[0]
    team_rows = st_df[st_df['TeamID'] == team_id]
    if team_rows.empty:
        return json.dumps({"error": "No standings data for this team."})
    row = team_rows.iloc[0]

    conference = row['Conference']
    conf_rank = int(row['PlayoffRank'])
    division = row['Division']
    wins = int(row['WINS'])
    losses = int(row['LOSSES'])

    status_line = f"Regular season - active ({conference} #{conf_rank}, {division})"
    try:
        series = commonplayoffseries.CommonPlayoffSeries(season=CURRENT_SEASON)
        series_df = series.get_data_frames()[0]
        if len(series_df) > 0:
            in_playoffs = (
                (series_df['HOME_TEAM_ID'] == team_id) |
                (series_df['VISITOR_TEAM_ID'] == team_id)
            ).any()
            if in_playoffs:
                status_line = f"Playoffs - {conference} #{conf_rank} seed (series details not parsed in Phase A)"
            else:
                status_line = "Offseason - did not qualify for playoffs"
    except Exception:
        pass

    return json.dumps({
        'team': team_info['full_name'],
        'abbreviation': team_info['abbreviation'],
        'status': status_line,
        'conference': conference,
        'conference_rank': conf_rank,
        'division': division,
        'record': f"{wins}-{losses}",
        'win_pct': round(wins / (wins + losses), 3) if (wins + losses) > 0 else 0.0,
    }, indent=2)


def get_team_season_stats(team_abbreviation: str) -> str:
    """Returns traditional per-game stats with NBA ranks (1-30).
    Ranks come directly from the nba_api endpoint.
    """
    team_info = get_team_info(team_abbreviation)
    if not team_info:
        return json.dumps({"error": f"Team '{team_abbreviation}' not found."})
    team_id = team_info['id']

    stats = leaguedashteamstats.LeagueDashTeamStats(
        measure_type_detailed_defense='Base',
        per_mode_detailed='PerGame',
        season=CURRENT_SEASON,
    )
    df = stats.get_data_frames()[0]
    rows = df[df['TEAM_ID'] == team_id]
    if rows.empty:
        return json.dumps({"error": "No season stats returned."})
    r = rows.iloc[0]

    def pack(val_col, rank_col, is_pct=False):
        v = float(r[val_col])
        return {
            'value': round(v * 100, 1) if is_pct else round(v, 1),
            'rank': int(r[rank_col]),
        }

    return json.dumps({
        'team': team_info['full_name'],
        'traditional_per_game': {
            'PPG': pack('PTS', 'PTS_RANK'),
            'FG_PCT': pack('FG_PCT', 'FG_PCT_RANK', is_pct=True),
            'FG3_PCT': pack('FG3_PCT', 'FG3_PCT_RANK', is_pct=True),
            'FT_PCT': pack('FT_PCT', 'FT_PCT_RANK', is_pct=True),
            'RPG': pack('REB', 'REB_RANK'),
            'APG': pack('AST', 'AST_RANK'),
            'SPG': pack('STL', 'STL_RANK'),
            'TOV_PG': pack('TOV', 'TOV_RANK'),
        }
    }, indent=2)


def get_team_advanced_stats(team_abbreviation: str) -> str:
    """Returns advanced metrics: Net Rating, Off/Def Rating from the Advanced
    measure type, plus eFG%, Opp eFG%, TOV% from Four Factors. Ranks included.
    """
    team_info = get_team_info(team_abbreviation)
    if not team_info:
        return json.dumps({"error": f"Team '{team_abbreviation}' not found."})
    team_id = team_info['id']

    adv = leaguedashteamstats.LeagueDashTeamStats(
        measure_type_detailed_defense='Advanced',
        per_mode_detailed='Per100Possessions',
        season=CURRENT_SEASON,
    )
    adv_df = adv.get_data_frames()[0]
    adv_row = adv_df[adv_df['TEAM_ID'] == team_id].iloc[0]

    ff = leaguedashteamstats.LeagueDashTeamStats(
        measure_type_detailed_defense='Four Factors',
        per_mode_detailed='PerGame',
        season=CURRENT_SEASON,
    )
    ff_df = ff.get_data_frames()[0]
    ff_row = ff_df[ff_df['TEAM_ID'] == team_id].iloc[0]

    def num(val, rank, is_pct=False):
        v = float(val)
        return {
            'value': round(v * 100, 1) if is_pct else round(v, 1),
            'rank': int(rank),
        }

    return json.dumps({
        'team': team_info['full_name'],
        'advanced': {
            'NET_RATING': num(adv_row['NET_RATING'], adv_row['NET_RATING_RANK']),
            'OFF_RATING': num(adv_row['OFF_RATING'], adv_row['OFF_RATING_RANK']),
            'DEF_RATING': num(adv_row['DEF_RATING'], adv_row['DEF_RATING_RANK']),
        },
        'four_factors': {
            'EFG_PCT': num(ff_row['EFG_PCT'], ff_row['EFG_PCT_RANK'], is_pct=True),
            'OPP_EFG_PCT': num(ff_row['OPP_EFG_PCT'], ff_row['OPP_EFG_PCT_RANK'], is_pct=True),
            'TM_TOV_PCT': num(ff_row['TM_TOV_PCT'], ff_row['TM_TOV_PCT_RANK'], is_pct=True),
        }
    }, indent=2)


def get_team_recent_games(team_abbreviation: str, num_games: int = 10) -> str:
    """Returns the team's last N games with per-game stats for short-term
    trend analysis.
    """
    team_info = get_team_info(team_abbreviation)
    if not team_info:
        return json.dumps({"error": f"Team '{team_abbreviation}' not found."})
    team_id = team_info['id']

    gl = teamgamelog.TeamGameLog(team_id=team_id, season=CURRENT_SEASON)
    df = gl.get_data_frames()[0].head(num_games)
    cols = ['GAME_DATE', 'MATCHUP', 'WL', 'PTS', 'FG_PCT', 'FG3_PCT', 'FT_PCT',
            'REB', 'AST', 'STL', 'TOV']
    keep = [c for c in cols if c in df.columns]
    return json.dumps(df[keep].to_dict(orient='records'), indent=2, default=str)


def get_team_players(team_abbreviation: str) -> str:
    """Returns top 7 players sorted by minutes played per game.
    Agent selects 3-5 for the Key Players section based on role fit.
    Includes FTA and FG3A for Force driver modifier and Sniper detection.
    """
    team_info = get_team_info(team_abbreviation)
    if not team_info:
        return json.dumps({"error": f"Team '{team_abbreviation}' not found."})
    team_id = team_info['id']

    p = leaguedashplayerstats.LeagueDashPlayerStats(
        season=CURRENT_SEASON,
        team_id_nullable=team_id,
        per_mode_detailed='PerGame',
    )
    df = p.get_data_frames()[0].sort_values('MIN', ascending=False).head(7)

    roster = commonteamroster.CommonTeamRoster(team_id=team_id, season=CURRENT_SEASON)
    rdf = roster.get_data_frames()[0]
    pos_map = dict(zip(rdf['PLAYER'], rdf['POSITION']))

    players = []
    for _, row in df.iterrows():
        name = row['PLAYER_NAME']
        players.append({
            'name': name,
            'position': pos_map.get(name, 'N/A'),
            'MPG': round(float(row['MIN']), 1),
            'PPG': round(float(row['PTS']), 1),
            'RPG': round(float(row['REB']), 1),
            'APG': round(float(row['AST']), 1),
            'SPG': round(float(row['STL']), 1),
            'BPG': round(float(row['BLK']), 1),
            'FTA': round(float(row['FTA']), 1),
            'FG3A': round(float(row['FG3A']), 1),
            'FG_PCT': round(float(row['FG_PCT']) * 100, 1),
            'FG3_PCT': round(float(row['FG3_PCT']) * 100, 1),
            'GP': int(row['GP']),
        })
    return json.dumps({'team': team_info['full_name'], 'players': players}, indent=2)


def get_team_injuries(team_name: str, today_date: str) -> str:
    """Searches for official injury reports and overnight updates for the
    given team. Agent parses returned sources and applies the injury logic
    defined in the system prompt.
    """
    q1 = f"{team_name} official injury report {today_date}"
    q2 = f"{team_name} NBA injury update post-game overnight {today_date}"

    search = TavilySearch(max_results=4, search_depth="advanced")
    r1 = search.invoke(q1)
    r2 = search.invoke(q2)
    return json.dumps({
        'official_report_search': r1,
        'overnight_update_search': r2,
    }, indent=2, default=str)


def get_analytical_articles(team_name: str, today_date: str) -> str:
    """Searches for last-24-hour analytical articles from credible sources only.
    Domain whitelist enforced server-side by Tavily.
    """
    query = f"{team_name} analysis opinion column breakdown strategy outlook -score -boxscore -live"
    search = TavilySearch(
        max_results=5,
        search_depth="advanced",
        include_domains=[
            "theathletic.com",
            "theringer.com",
            "espn.com",
            "nba.com",
            "sports.yahoo.com",
            "cbssports.com",
        ],
    )
    return json.dumps(search.invoke(query), indent=2, default=str)