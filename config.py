from nba_api.stats.static import teams

CURRENT_SEASON = '2025-26'

_all_teams = teams.get_teams()
TEAM_ALIASES = {}
_city_seen = {}

for _t in _all_teams:
    abbr = _t['abbreviation']
    TEAM_ALIASES[abbr.lower()] = abbr
    TEAM_ALIASES[_t['nickname'].lower()] = abbr
    TEAM_ALIASES[_t['full_name'].lower()] = abbr
    city = _t['city'].lower()
    if city in _city_seen and _city_seen[city] != abbr:
        TEAM_ALIASES.pop(city, None)
    else:
        TEAM_ALIASES[city] = abbr
        _city_seen[city] = abbr


def resolve_team(query: str) -> str | None:
    if not query:
        return None
    return TEAM_ALIASES.get(query.strip().lower())


def get_team_info(abbreviation: str) -> dict | None:
    return next(
        (t for t in _all_teams if t['abbreviation'] == abbreviation.upper()),
        None,
    )