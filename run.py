import sys
from datetime import datetime
from config import resolve_team, get_team_info
from agent import agent_executor


def run_report(team_query: str) -> str:
    abbr = resolve_team(team_query)
    if not abbr:
        return (
            f"Could not identify team from '{team_query}'. "
            f"Provide an NBA team name, city, nickname, or 3-letter abbreviation."
        )

    team_info = get_team_info(abbr)
    full_name = team_info['full_name']
    today_str = datetime.now().strftime("%d %B %Y")

    user_msg = (
        f"Generate the daily report for team abbreviation {abbr} "
        f"(full name: {full_name}). Today's date is {today_str}.\n\n"
        f"ABSOLUTE OUTPUT RULE — NON-NEGOTIABLE:\n"
        f"The VERY FIRST CHARACTER of your response MUST be the basketball emoji 🏀.\n"
        f"Do NOT write any preamble, analysis notes, calculation steps, or reasoning "
        f"before the header. All of your reasoning happens internally (tool calls + "
        f"thinking) — your FINAL response to me must start with:\n"
        f"🏀 {full_name.upper()} — DAILY REPORT\n\n"
        f"If you find yourself writing 'Now I will...', 'Let me calculate...', "
        f"'Let me analyze...', or anything similar — STOP and restart with just the header. "
        f"The report must be fully self-contained; no meta-commentary allowed."
    )

    response = agent_executor.invoke({"messages": [("user", user_msg)]})
    return response["messages"][-1].content


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <team name or abbreviation>")
        print("Examples:")
        print("  python run.py Celtics")
        print("  python run.py \"Los Angeles Lakers\"")
        print("  python run.py BOS")
        sys.exit(1)

    team_query = " ".join(sys.argv[1:])

    print(f"Generating report for: {team_query}")
    print(f"Today: {datetime.now().strftime('%d %B %Y')}")
    print("=" * 60)
    print("Working (may take 30-90 seconds — agent is calling tools)...")
    print("=" * 60)

    report = run_report(team_query)

    print("\n")
    print(report)
    print("\n")


if __name__ == "__main__":
    main()