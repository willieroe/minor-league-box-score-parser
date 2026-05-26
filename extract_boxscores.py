# extract_boxscores.py
# Baseball Box Score Parser for historical minor league data (Retrosheet-inspired CSV output)
#
# Supports: Full box scores, minimal RHE / R-only / line-score-only formats,
#           postponements, and both pre-game and post-official forfeits.
#
# Developed iteratively May 2026 for the "Parsing box scores" project.
# Cleaned & hardened version.

import os
import re
import csv
import configparser
from datetime import datetime
import logging

# Setup logging with WARNING level to reduce noise
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# === Constants for CSV fieldnames (centralized for maintainability) ===
GAMEINFO_FIELDNAMES = [
    'gid', 'visteam', 'hometeam', 'site', 'date', 'number', 'starttime', 'daynight', 'innings',
    'tiebreaker', 'userdh', 'htbf', 'timeofgame', 'attendance', 'fieldcond', 'precip', 'sky',
    'temp', 'winddir', 'windspeed', 'oscorer', 'forfeit', 'suspend', 'umphome', 'ump1b',
    'ump2b', 'ump3b', 'umplf', 'umprf', 'wp', 'lp', 'save', 'gametype', 'vruns', 'hruns',
    'wteam', 'lteam', 'line', 'batteries', 'lineups', 'box', 'php', 'season', 'source', 'status',
    'status-reason'
]

TEAMSTATS_FIELDNAMES = [
    'gid', 'team', 'inn1', 'inn2', 'inn3', 'inn4', 'inn5', 'inn6', 'inn7', 'inn8', 'inn9',
    'inn10', 'inn11', 'inn12', 'inn13', 'inn14', 'inn15', 'inn16', 'inn17', 'inn18', 'inn19',
    'inn20', 'inn21', 'inn22', 'inn23', 'inn24', 'inn25', 'inn26', 'inn27', 'inn28', 'lob',
    'mgr', 'stattype', 'b_pa', 'b_ab', 'b_r', 'b_h', 'b_d', 'b_t', 'b_hr', 'b_rbi', 'b_sh',
    'b_sf', 'b_hbp', 'b_w', 'b_iw', 'b_k', 'b_sb', 'b_cs', 'b_gdp', 'b_xi', 'b_roe', 'b_er', 'p_ipouts',
    'p_noout', 'p_bfp', 'p_h', 'p_d', 'p_t', 'p_hr', 'p_r', 'p_er', 'p_w', 'p_iw', 'p_k',
    'p_hbp', 'p_wp', 'p_bk', 'p_sh', 'p_sf', 'p_sb', 'p_cs', 'p_pb', 'd_po', 'd_a', 'd_e',
    'd_dp', 'd_tp', 'd_pb', 'd_wp', 'd_sb', 'd_cs', 'start_l1', 'start_l2', 'start_l3',
    'start_l4', 'start_l5', 'start_l6', 'start_l7', 'start_l8', 'start_l9', 'start_f1',
    'start_f2', 'start_f3', 'start_f4', 'start_f5', 'start_f6', 'start_f7', 'start_f8',
    'start_f9', 'start_f10', 'date', 'number', 'site', 'vishome', 'opp', 'win', 'loss',
    'tie', 'gametype', 'box', 'pbp', 'source'
]


def create_minimal_gameinfo_row(gid, game_data, team_abbr):
    """
    Build a minimal gameinfo row for postponed games and pre-game (Type 1) forfeits.
    Used by the early-exit paths in write_csvs().
    """
    return {
        'gid': gid,
        'visteam': team_abbr.get(game_data['metadata']['away'], 'UNK'),
        'hometeam': team_abbr.get(game_data['metadata']['home'], 'UNK'),
        'site': game_data['metadata']['site'] or '',
        'date': game_data['metadata']['date'],
        'number': game_data['metadata']['number'],
        'starttime': '',
        'daynight': 'day',
        'innings': '',
        'tiebreaker': '',
        'userdh': '',
        'htbf': '',
        'timeofgame': '',
        'attendance': '',
        'fieldcond': '',
        'precip': '',
        'sky': '',
        'temp': '',
        'winddir': '',
        'windspeed': '',
        'oscorer': '',
        'forfeit': game_data['metadata'].get('forfeit', ''),
        'suspend': '',
        'umphome': game_data['metadata']['umpires'][0] if game_data['metadata']['umpires'] else '',
        'ump1b': '',
        'ump2b': '',
        'ump3b': '',
        'umplf': '',
        'umprf': '',
        'wp': '',
        'lp': '',
        'save': '',
        'gametype': game_data['metadata']['gametype'],
        'vruns': '',
        'hruns': '',
        'wteam': game_data['metadata'].get('wteam', ''),
        'lteam': game_data['metadata'].get('lteam', ''),
        'line': '',
        'batteries': '',
        'lineups': 'n',
        'box': 'n',
        'php': '',
        'season': game_data['metadata']['date'][:4] if game_data['metadata']['date'] else '',
        'source': game_data['metadata']['source'],
        'status': game_data['metadata']['status'],
        'status-reason': game_data['metadata']['status-reason']
    }


def setup_config():
    """Load configuration from config.ini."""
    config = configparser.ConfigParser()
    config.read('config.ini')
    return {
        'boxscore_folder': config.get('DEFAULT', 'boxscore_folder', fallback='boxscores'),
        'output_dir': config.get('DEFAULT', 'output_dir', fallback='output'),
        'team_abbreviations': config.get('DEFAULT', 'team_abbreviations', fallback='team_abbreviations.csv')
    }

def load_team_abbreviations(file_path):
    """Load team abbreviations from CSV."""
    team_abbr = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                team_abbr[row['team_name']] = row['abbreviation']
    except FileNotFoundError:
        logging.error(f"Team abbreviations file {file_path} not found.")
        raise
    return team_abbr

def parse_ip(ip_str):
    """Convert innings pitched (e.g., #7.1) to outs."""
    try:
        ip = float(ip_str.strip('#'))
        full_innings = int(ip)
        partial = ip - full_innings
        return full_innings * 3 + int(partial * 10)
    except ValueError:
        logging.warning(f"Invalid IP format: {ip_str}")
        return 0

def parse_time_to_minutes(time_str):
    """Convert time (e.g., 2:05) to minutes."""
    try:
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except ValueError:
        logging.warning(f"Invalid time format: {time_str}")
        return None

def get_defensive_outs(team, game_data):
    """Compute total defensive outs from line score (last resort for minimal RHE).
    Formula: 3 * (number of innings the opponent batted, ignoring 'x' which means no half-inning played).
    Used ONLY if no explicit P_IP (pitching_stats) AND team_po not present in TOTALS (so team_po + B_XO can't be derived).
    Also used as validation cross-check in full boxes (logs discrepancy if explicit and derived differ >3 outs).
    Returns '' (NULL) if no line score data is present to derive innings played from.
    """
    if 'line_scores' not in game_data or not game_data.get('line_scores'):
        return ''
    opponent = game_data['metadata']['home'] if team == game_data['metadata']['away'] else game_data['metadata']['away']
    if opponent not in game_data['line_scores']:
        return ''
    inns = game_data['line_scores'][opponent].get('innings', [])
    valid_inns = [i for i in inns if i is not None]  # 'x' -> None means no half-inning, 0 outs
    if not valid_inns:
        return ''
    return len(valid_inns) * 3

def extract_lname_initial(name_str):
    """Helper to extract lname and initial from cleaned name string."""
    parts = [p for p in name_str.replace(',', ' ').split() if p]
    if not parts:
        return '', None
    lname = parts[-1].lower()
    initial = parts[0].rstrip('.').lower() if len(parts) > 1 and parts[0].endswith('.') else None
    return lname, initial

def standardize_player_id(match_id, identifier=None, team=None, player_team=None, gid="Unknown"):
    """Convert matchID to playerID format, handling initials and single names.

    This function is defensive against transcription/OCR noise such as
    stray brackets or braces that sometimes appear in historical box scores
    (e.g. 'Smith[JON}' or 'O'Neill[1]').
    """
    match_id = match_id.strip().rstrip(',')

    # Defensive cleaning for noisy transcriptions (e.g. 'Smith[JON}' or 'O'Neill[1]')
    # If brackets/braces are present and no identifier was passed in, try to extract one.
    if not identifier and ('[' in match_id or '{' in match_id):
        # Extract content from first bracket/brace group as identifier
        m = re.search(r'[\[{](.+?)[\]}]', match_id)
        if m:
            identifier = m.group(1).strip()
        # Remove bracket/brace junk and collapse multiple spaces
        match_id = re.sub(r'[\[\]{}]', ' ', match_id)
        match_id = re.sub(r'\s+', ' ', match_id).strip()

        # If after cleaning we have multiple tokens and no dot-initial,
        # keep only the first token as the name (the rest was likely identifier junk)
        tokens = match_id.split()
        if len(tokens) > 1 and not any(t.endswith('.') for t in tokens):
            match_id = tokens[0]

    if not match_id:
        logging.warning(f"[gid={gid}] Empty player ID encountered")
        return "Unknown"

    parts = [p for p in match_id.replace(',', ' ').split() if p]
    if not parts:
        logging.warning(f"[gid={gid}] Invalid player ID format: {match_id}")
        return "Unknown"

    lname = None
    initial = None
    player_id = "Unknown"

    if len(parts) == 2:
        if parts[1].endswith('.'):
            lname = parts[0]
            initial = parts[1].rstrip('.')
            player_id = f"{lname}, {initial}"
        elif parts[0].endswith('.'):
            initial = parts[0].rstrip('.')
            lname = parts[1]
            player_id = f"{lname}, {initial}"
    elif len(parts) == 1:
        lname = parts[0]
        player_id = lname
    else:
        lname = parts[-1]
        initial = parts[0].rstrip('.') if len(parts) > 1 and parts[0].endswith('.') else None
        player_id = f"{lname}, {initial}" if initial else lname

    if identifier:
        # Clean any stray brackets that may have leaked into the identifier
        clean_identifier = re.sub(r'[\[\]{}]', '', identifier).strip()
        if clean_identifier:
            player_id += f"[{clean_identifier}]"

    if team and player_team and player_id != "Unknown":
        for pid, pteam in player_team.items():
            pid_clean = re.sub(r'\[.*?\]', '', pid).strip()
            pid_lname, pid_initial = extract_lname_initial(pid_clean)
            if pteam == team and lname.lower() == pid_lname and initial and pid_initial and initial.lower() == pid_initial:
                return pid
    return player_id

def parse_boxscore(boxscore_text, team_abbr):
    """
    Parse a single historical box score text into structured data.

    Supports:
    - Full / maximum box scores with player lines, TOTALS, and line scores
    - Minimal formats (RHE, R-only, line-score only, no line score)
    - Postponed games (status: postponed)
    - Pre-game forfeits (status: forfeit + forfeit-to: home|away)
    - Post-official forfeits (full box score + forfeit flag)

    Returns a dict with metadata, teams, line_scores, batting/pitching/fielding stats,
    and discrepancy logs. Does not write any CSV files.
    """
    game_data = {
        'metadata': {
            'date': '', 'number': 0, 'league': '', 'away': '', 'home': '', 'source': '',
            'attendance': None, 'site': None, 'status': 'final', 'status-reason': '', 'forfeit-to': '', 'gametype': 'regular',
            'batted-first': None, 'time': None, 'umpires': [], 'outsatend': None
        },
        'notes': [],
        'teams': {}, 'line_scores': {}, 'batting_stats': [], 'pitching_stats': [], 'fielding_stats': [],
        'discrepancies': []
    }
    incomplete_lineups = set()
    teams_initialized = False
    lines = boxscore_text.strip().split('\n')
    current_team = None
    team_headers = {}
    player_team = {}
    lineup_positions = {}
    parsing_metadata = True
    dp_counts = {}
    dp_events = {}  # List for counting unique double and triple play events per team

    gid = "Unknown"

    for line in lines:
        if ':' in line and not re.match(r'^\w+:.*\b(ab|r|h|po|a|e|rbi|sb|sh)\b', line):
            key, value = map(str.strip, line.split(':', 1))
            if key == 'date':
                try:
                    datetime.strptime(value, '%Y-%m-%d')
                    game_data['metadata']['date'] = value.replace('-', '')
                except ValueError:
                    logging.warning(f"[gid=Unknown] Invalid date format: {value}")
                    return None
            elif key == 'number':
                game_data['metadata']['number'] = int(value) if value.isdigit() else 0
            elif key == 'league':
                game_data['metadata']['league'] = value
            elif key == 'away':
                game_data['metadata']['away'] = value
                game_data['teams'][value] = game_data['teams'].get(value, {'players': [], 'totals': None})
            elif key == 'home':
                game_data['metadata']['home'] = value
                game_data['teams'][value] = game_data['teams'].get(value, {'players': [], 'totals': None})
                home_abbr = team_abbr.get(value, 'UNK')
                teams_initialized = True
                gid = f"{home_abbr}{game_data['metadata']['date']}{game_data['metadata']['number']}"
            elif key == 'source':
                game_data['metadata']['source'] = value
            elif key == 'A':
                game_data['metadata']['attendance'] = int(value) if value.isdigit() else None
            elif key == 'site':
                game_data['metadata']['site'] = value
            elif key == 'status':
                game_data['metadata']['status'] = value.lower()
            elif key == 'forfeit-to':
                game_data['metadata']['forfeit-to'] = value.lower()
                # Set winner and loser immediately
                if game_data['metadata']['forfeit-to'] == 'home':
                    game_data['metadata']['wteam'] = game_data['metadata']['home']
                    game_data['metadata']['lteam'] = game_data['metadata']['away']
                elif game_data['metadata']['forfeit-to'] == 'away':
                    game_data['metadata']['wteam'] = game_data['metadata']['away']
                    game_data['metadata']['lteam'] = game_data['metadata']['home']
            elif key == 'status-reason':
                game_data['metadata']['status-reason'] = value
            elif key == 'gametype':
                game_data['metadata']['gametype'] = value
            elif key == 'batted-first':
                game_data['metadata']['batted-first'] = value
            elif key == 'T':
                game_data['metadata']['time'] = parse_time_to_minutes(value)
            elif key == 'U':
                game_data['metadata']['umpires'] = [u.strip() for u in value.split(';')]
            elif key == 'outsatend':
                game_data['metadata']['outsatend'] = int(value.strip('#')) if value else None

    if not teams_initialized:
        logging.error(f"[gid={gid}] No teams initialized during metadata parsing, skipping boxscore")
        return None
    if not game_data['metadata']['away'] or not game_data['metadata']['home']:
        logging.error(f"[gid={gid}] Missing away or home team metadata, skipping boxscore")
        return None

    for line in lines:
        line = line.strip()
        if not line or line.startswith('---'):
            current_team = None
            continue
        if line.startswith('note:') or line.startswith('recap_'):
            game_data['notes'].append({'gid': gid, 'text': line})
            continue
        if line.startswith(('T:', 'U:', 'outsatend:')):
            key, value = map(str.strip, line.split(':', 1))
            if key == 'T':
                game_data['metadata']['time'] = parse_time_to_minutes(value)
            elif key == 'U':
                game_data['metadata']['umpires'] = [u.strip() for u in value.split(';')]
            elif key == 'outsatend':
                game_data['metadata']['outsatend'] = int(value.strip('#')) if value else None
            continue
        # Only trigger on lines that clearly look like team stat headers (reject lines starting with "line:")
        if re.match(r"^[A-Za-z][A-Za-z'.\s,-]+:\s*(ab|r|h|po|a|e|rbi|sb|sh|2b|3b)", line, re.IGNORECASE) and not line.lower().startswith('line:'):
            header_match = re.match(r"^([A-Za-z][A-Za-z'.\s,-]+):\s*(.+)$", line)
            if header_match:
                team_name = header_match.group(1).strip()
                header_raw = header_match.group(2).strip().upper()

                known_non_team = {'line', 'date', 'number', 'league', 'away', 'home', 'source',
                                  'batteries', 'lineups', 'box', 'php', 'season'}

                if team_name.lower() not in known_non_team:
                    # Normalize tokens
                    raw_tokens = re.findall(r'[A-Za-z0-9]+', header_raw)
                    header = []
                    for tok in raw_tokens:
                        tok = tok.strip()
                        if tok in ('AB', 'ATBAT', 'AT-BAT'):
                            header.append('ab')
                        elif tok == 'R':
                            header.append('r')
                        elif tok == 'H':
                            header.append('h')
                        elif tok in ('PO', 'P', 'OUTS'):
                            header.append('po')
                        elif tok == 'A':
                            header.append('a')
                        elif tok == 'E':
                            header.append('e')
                        elif tok in ('RBI', 'RBIS'):
                            header.append('rbi')
                        elif tok in ('SB', 'SBS', 'STOLEN'):
                            header.append('sb')
                        elif tok in ('SH', 'SHS', 'SACRIFICE'):
                            header.append('sh')
                        elif tok in ('2B', 'DB', 'DOUBLES'):
                            header.append('2b')
                        elif tok in ('3B', 'TB', 'TRIPLES'):
                            header.append('3b')
                        else:
                            header.append(tok.lower())

                    if header:
                        parsing_metadata = False
                        current_team = team_name
                        team_headers[current_team] = header
                        game_data['teams'][current_team] = {'players': [], 'totals': None}
                        lineup_positions[current_team] = {}
                        continue
        elif current_team and re.match(r'^TOTALS:', line):
            stats = line.replace('TOTALS:', '').strip().split()
            stats = [int(s) if s.isdigit() else 0 for s in stats]
            game_data['teams'][current_team]['totals'] = dict(zip(team_headers[current_team], stats))
            expected = len(team_headers.get(current_team, []))
            if len(stats) < expected:
                stats += [0] * (expected - len(stats))
            elif len(stats) > expected:
                stats = stats[:expected]
        elif current_team and '@' in line:
            match = re.match(r'(\(~([\d.]+)\))?[*+^&$]?([^@]+)(\[([A-Za-z0-9]{1,3})\])? @ ([^:]+):[\t ]+(.+)', line)
            if match:
                try:
                    lineup_pos, _, player_id, identifier_group, identifier, pos, stats = match.groups()
                except ValueError as e:
                    logging.warning(f"[gid={gid}] Failed to unpack roster line: {line}, error: {e}")
                    continue
                # logging.warning(f"[gid={gid}] Parsing roster line: {line}, player_id='{player_id}', team={current_team}, pos={pos}")
                if not player_id.strip() or not re.match(r"[A-Za-z][A-Za-z'.\s,-]*[A-Za-z]", player_id.strip()):
                    logging.warning(f"[gid={gid}] Skipping invalid player ID in roster line: {line}")
                    continue
                stats = stats.strip().split()
                # Treat 'x'/'X' (common in minimal/old box scores) as None - 5/10/26 fix
                stats = [int(s) if s.isdigit() else None for s in stats]
                expected_len = len(team_headers.get(current_team, []))
                if len(stats) < expected_len:
                    stats += [0] * (expected_len - len(stats))
                elif len(stats) > expected_len:
                    stats = stats[:expected_len]
                player_stats = dict(zip(team_headers[current_team], stats))
                player_stats['position'] = pos
                player_stats['player_id'] = standardize_player_id(player_id.strip(), identifier, current_team, player_team, gid)
                if player_stats['player_id'] == "Unknown":
                    logging.warning(f"[gid={gid}] Skipping invalid player ID after standardization: {line}")
                    continue
                player_stats['identifier'] = identifier if identifier else None
                lineup_pos = lineup_pos[2:-1] if lineup_pos else None
                b_seq = 1
                seq = 1
                has_lineup_pos = bool(lineup_pos)
                if lineup_pos:
                    lp, seq = lineup_pos.split('.')
                    lp = int(lp)
                    seq = int(seq)
                    b_seq = seq
                else:
                    lp = len([p for p in game_data['teams'][current_team]['players'] if p['b_seq'] == 1]) + 1
                    # b_lp set to '' when no batting order spot info provided in box score (e.g. minimal RHE with only 2 players listed)
                player_stats['b_seq'] = b_seq
                player_stats['b_lp'] = lp
                player_stats['seq'] = seq
                player_stats['has_lineup_pos'] = has_lineup_pos
                player_stats['is_pitcher'] = bool(re.match(r'^(p|p-.*|.*-p)$', pos))
                game_data['teams'][current_team]['players'].append(player_stats)
                player_team[player_stats['player_id']] = current_team
                if lp and lp not in lineup_positions[current_team]:
                    lineup_positions[current_team][lp] = {}
                if lp:
                    lineup_positions[current_team][lp][b_seq] = player_stats['player_id']
        elif re.match(r'^line:\s*[^:]+:\s*.+-\s*\d+$', line.strip(), re.IGNORECASE):
            parts = line.split(':', 1)
            if parts[0].strip() != 'line':
                logging.warning(f"[gid={gid}] Skipped line score (missing line: prefix): {line}")
                continue
            subparts = parts[1].split(':', 1)
            if len(subparts) < 2:
                logging.warning(f"[gid={gid}] Malformed line score (missing team): {line}")
                continue
            team = subparts[0].strip()
            scores_str = subparts[1].strip()
            if not scores_str or scores_str == '-':
                logging.warning(f"[gid={gid}] Malformed line score (missing runs): {line}")
                continue
            innings_str, runs_str = scores_str.rsplit('-', 1)
            innings_str = innings_str.strip()
            runs_str = runs_str.strip()
            try:
                runs = int(runs_str) if runs_str.isdigit() else 0
            except ValueError:
                logging.warning(f"[gid={gid}] Malformed runs in line score: {line}")
                runs = 0
            if innings_str:
                innings = innings_str.split()
                if not all(i.isdigit() or i.lower() == 'x' for i in innings):
                    logging.warning(f"[gid={gid}] Malformed innings in line score (non-digits): {line}")
                    continue
                innings = [int(i) if i.isdigit() else None for i in innings]
            else:
                innings = []
            game_data['line_scores'][team] = {'innings': innings, 'runs': runs}
        elif line.startswith('B_') or line.startswith('P_') or line.startswith('F_'):
            stat_type = line.split(':', 1)[0]
            stat_data = line.split(':', 1)[1].strip()
            if stat_type in ['B_LOB', 'B_ROE', 'B_ER']:
                for entry in stat_data.split(';'):
                    entry = entry.strip()
                    if not entry:
                        continue
                    # Format: "Atlanta #4" or "Birmingham #3"
                    parts = entry.split('#')
                    if len(parts) == 2:
                        team_name = parts[0].strip()
                        try:
                            count = int(parts[1].strip())
                        except ValueError:
                            count = 0
                        if team_name in game_data['teams']:
                            if 'team_events' not in game_data['teams'][team_name]:
                                game_data['teams'][team_name]['team_events'] = {}
                            key = stat_type[2:].lower()  # lob, roe, er
                            game_data['teams'][team_name]['team_events'][key] = count
                continue  # Skip adding to batting_stats
            if stat_type in ['F_DP', 'F_TP']:
                for play_event in stat_data.split(';'):
                    play_event = play_event.strip()
                    if not play_event:
                        continue
                    # Determine team based on first player in the event
                    first_player = play_event.split(',')[0].strip()
                    identifier = None
                    if '[' in first_player and ']' in first_player:
                        first_player, identifier_group = first_player.split('[')
                        identifier = identifier_group.strip(']')
                    player_id = standardize_player_id(first_player, identifier, None, player_team, gid)
                    team = player_team.get(player_id)
                    if not team:
                        logging.warning(f"[gid={gid}] Unmatched player in {stat_type}: {first_player} (standardized: {player_id}, available: {list(player_team.keys())})")
                        continue
                    event_id = f"{team}_{stat_type}_{play_event}"
                    dp_events.setdefault(team, []).append(event_id)
                    # Assign individual player counts for DP/TP
                    for stat in play_event.split(','):
                        stat = stat.strip()
                        if stat:
                            player_id = standardize_player_id(stat, identifier, team, player_team, gid)
                            if player_id != "Unknown":
                                key = (player_id, team, stat_type[2:])
                                dp_counts[key] = dp_counts.get(key, 0) + 1
            else:
                for stat in stat_data.split(';'):
                    stat = stat.strip()
                    if not stat:
                        continue
                    count = 1
                    if '#' in stat:
                        stat, count_str = stat.split('#')
                        count = parse_ip(count_str) if stat_type == 'P_IP' else int(count_str)
                    stat = stat.lstrip('~')
                    identifier = None
                    if '[' in stat and ']' in stat:
                        stat, identifier_group = stat.split('[', 1)
                        identifier = identifier_group.split(']')[0].strip()
                    player_id = standardize_player_id(stat, identifier, current_team, player_team, gid)
                    if player_id == "Unknown":
                        logging.warning(f"[gid={gid}] Skipping invalid player in stat {stat_type}: {stat}")
                        continue
                    team = player_team.get(player_id)
                    if not team:
                        stat_lname, stat_initial = extract_lname_initial(stat)
                        for pid, pteam in player_team.items():
                            pid_clean = re.sub(r'\[.*?\]', '', pid).strip()
                            pid_lname, pid_initial = extract_lname_initial(pid_clean)
                            if pteam == current_team and stat_lname == pid_lname and stat_initial and pid_initial and stat_initial == pid_initial:
                                player_id = pid
                                team = pteam
                                break
                    if not team:
                        logging.warning(f"[gid={gid}] Unmatched player in stat {stat_type}: {stat} (standardized: {player_id}, available: {list(player_team.keys())})")
                        continue
                    if stat_type.startswith('B_'):
                        game_data['batting_stats'].append({
                            'player_id': player_id, 'team': team, 'stat': stat_type[2:], 'count': count
                        })
                    elif stat_type.startswith('P_'):
                        game_data['pitching_stats'].append({
                            'player_id': player_id, 'team': team, 'stat': stat_type[2:], 'count': count
                        })
                    elif stat_type.startswith('F_'):
                        game_data['fielding_stats'].append({
                            'player_id': player_id, 'team': team, 'stat': stat_type[2:], 'count': count
                        })

    for (player_id, team, stat), count in dp_counts.items():
        game_data['fielding_stats'].append({
            'player_id': player_id, 'team': team, 'stat': stat, 'count': count
        })

    for team, data in game_data['teams'].items():
        if data['totals']:
            # Initialize sums only for the stats we care about validating
            player_sums = {'ab': 0, 'r': 0, 'h': 0, 'po': 0, 'a': 0, 'e': 0, 'rbi': 0}

            for player in data['players']:
                for stat in player_sums:
                    # This is the key fix you asked about:
                    if stat in player and player[stat] is not None:
                        player_sums[stat] += player[stat]

            # Now compare the cleaned player sum against the TOTALS line
            for stat in player_sums:
                if stat in data['totals'] and data['totals'][stat] != player_sums[stat]:
                    game_data['discrepancies'].append({
                        'gid': gid,
                        'team': team_abbr.get(team, team),
                        'discrepancy': f"player {stat.upper()} sum to {player_sums[stat]}, "
                                       f"TOTALS {stat.upper()} {data['totals'][stat]}"
                    })
    # Final detection of incomplete lineups (for minimal RHE-style where <9 players or incomplete positions)
    # This ensures b_lp='' in batting.csv and clears start_l* for such cases, while full lineups (even without (~X.X) markers) keep 1-9
    for team, data in game_data['teams'].items():
        players = data.get('players', [])
        if players:
            lp_values = [p['b_lp'] for p in players]
            max_lp = max(lp_values, default=0)
            unique_lps = len(set(lp_values))
            player_count = len(players)
            if max_lp != 9 or unique_lps != 9 or player_count < 9:
                incomplete_lineups.add(team)
                lineup_positions[team] = {}  # ensure start_l1..9 are blank for incomplete lineups
        # Validation cross-check for defensive outs / p_ipouts (user requested for full boxes)
        # Logs to discrepancies.csv if explicit (P_IP or team_po) and derived line-score value differ by >3 outs.
        # This helps catch data entry errors in historical box scores while not overriding explicit values.
        # Use safe access to vars defined in try block (in case of early return paths)
        pitchers_per_team = locals().get('pitchers_per_team', {}) or {}
        pitching_data = locals().get('pitching_data', []) or []
        for team in game_data['teams']:
            derived = get_defensive_outs(team, game_data)
            if derived in (0, ''):
                continue
            # Check explicit from sole pitcher p_ipouts (set either from P_IP or our RHE fallback above)
            explicit = None
            if len(pitchers_per_team.get(team, [])) == 1:
                for p in pitching_data:
                    if p.get('team') == team_abbr.get(team, team):
                        explicit = p.get('p_ipouts', 0)
                        break
            if explicit is not None and explicit != 0 and abs(explicit - derived) > 3:
                game_data['discrepancies'].append({
                    'gid': gid,
                    'team': team_abbr.get(team, team),
                    'discrepancy': f"defensive outs: explicit P_IP {explicit} vs derived from line score {derived} (full box cross-check)"
                })
            else:
                # Also check vs team_po if present (for non-pitcher or aggregate)
                explicit_po = (game_data['teams'].get(team, {}).get('totals') or {}).get('po')
                if explicit_po is not None and explicit_po != 0 and abs(explicit_po - derived) > 3:
                    game_data['discrepancies'].append({
                        'gid': gid,
                        'team': team_abbr.get(team, team),
                        'discrepancy': f"defensive outs: explicit team_po {explicit_po} vs derived from line score {derived} (full box cross-check)"
                    })
    # logging.warning(f"[gid={gid}] Final player_team: {player_team}")
    return game_data, gid, lineup_positions, dp_counts, player_team, incomplete_lineups, dp_events

# helper function
def safe_val(v, default=''):
    return v if v is not None else default

def write_csvs(game_data, gid, lineup_positions, team_abbr, output_dir, dp_counts, player_team, incomplete_lineups, dp_events):
    """
    Write the parsed game data to the output CSV files.

    Handles both normal games and special cases:
    - Normal full or minimal box scores → full set of CSVs
    - Postponed games (no play data) → only gameinfo.csv
    - Pre-game forfeits (Type 1) → gameinfo.csv + minimal teamstats.csv with win/loss
    - Post-official forfeits (Type 2) → normal output + forfeit='Y' in gameinfo.csv

    Uses centralized GAMEINFO_FIELDNAMES and TEAMSTATS_FIELDNAMES constants.
    """
    os.makedirs(output_dir, exist_ok=True)

    # === Early exit ONLY for pre-game (Type 1) forfeits ===
    if (game_data['metadata'].get('status', '').lower() == 'forfeit'
            and all(not data.get('players') for data in game_data.get('teams', {}).values())):

        gameinfo = create_minimal_gameinfo_row(gid, game_data, team_abbr)

        # Write gameinfo.csv
        with open(os.path.join(output_dir, 'gameinfo.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=GAMEINFO_FIELDNAMES)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(gameinfo)

            # Write minimal teamstats.csv (no umpire field)
            teamstats_rows = []
            for t in [game_data['metadata']['away'], game_data['metadata']['home']]:
                row = {
                    'gid': gid,
                    'team': team_abbr.get(t, t),
                    # add vishome and opp
                    'vishome': 'v' if game_data['metadata']['away'] == t else 'h',
                    'opp': team_abbr.get(game_data['metadata']['home'], game_data['metadata']['home']) if t == game_data['metadata']['away'] else
                        team_abbr.get(game_data['metadata']['away'], game_data['metadata']['away']),
                    'win': '1' if game_data['metadata'].get('wteam') == t else '',
                    'loss': '1' if game_data['metadata'].get('lteam') == t else '',
                    'date': game_data['metadata']['date'],
                    'number': game_data['metadata']['number'],
                    'gametype': game_data['metadata']['gametype'],
                    'source': game_data['metadata']['source']
                }
                teamstats_rows.append(row)

            with open(os.path.join(output_dir, 'teamstats.csv'), 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=TEAMSTATS_FIELDNAMES)
                if f.tell() == 0:
                    writer.writeheader()
                for row in teamstats_rows:
                    writer.writerow(row)
        return
    # === End of Type 1 forfeit early exit ===

    # === Early exit for postponed / abandoned / other games ===
    if game_data['metadata']['status'].lower() in ['postponed', 'abandoned', 'other']:
        # Write ONLY gameinfo.csv and exit immediately.
        # This prevents teamstats.csv (and batting/pitching/fielding) from being written.
        gameinfo = create_minimal_gameinfo_row(gid, game_data, team_abbr)

        with open(os.path.join(output_dir, 'gameinfo.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=GAMEINFO_FIELDNAMES)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(gameinfo)
        return
        # === End of early exit ===

        with open(os.path.join(output_dir, 'gameinfo.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=GAMEINFO_FIELDNAMES)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(gameinfo)
        return
    # === End of early exit for postponed games ===

    gameinfo = {
        'gid': gid,
        'visteam': team_abbr.get(game_data['metadata']['away'], 'UNK'),
        'hometeam': team_abbr.get(game_data['metadata']['home'], 'UNK'),
        'site': game_data['metadata']['site'] or '',
        'date': game_data['metadata']['date'],
        'number': game_data['metadata']['number'],
        'starttime': '',
        'daynight': 'day',
        'innings': '',
        'tiebreaker': '',
        'userdh': '',
        'htbf': 'y' if game_data['metadata']['batted-first'] == 'home' else '',
        'timeofgame': game_data['metadata']['time'] or '',
        'attendance': game_data['metadata']['attendance'] or '',
        'fieldcond': '',
        'precip': '',
        'sky': '',
        'temp': '',
        'winddir': '',
        'windspeed': '',
        'oscorer': '',
        'forfeit': '',
        'suspend': '',
        'umphome': game_data['metadata']['umpires'][0] if game_data['metadata']['umpires'] else '',
        'ump1b': game_data['metadata']['umpires'][1] if len(game_data['metadata']['umpires']) > 1 else '',
        'ump2b': game_data['metadata']['umpires'][2] if len(game_data['metadata']['umpires']) > 2 else '',
        'ump3b': game_data['metadata']['umpires'][3] if len(game_data['metadata']['umpires']) > 3 else '',
        'umplf': game_data['metadata']['umpires'][4] if len(game_data['metadata']['umpires']) > 4 else '',
        'umprf': game_data['metadata']['umpires'][5] if len(game_data['metadata']['umpires']) > 5 else '',
        'wp': '',
        'lp': '',
        'save': '',
        'gametype': game_data['metadata']['gametype'],
        'vruns': 0,
        'hruns': 0,
        'wteam': '',
        'lteam': '',
        'line': 'y' if game_data['line_scores'] else '',
        'batteries': '',
        'lineups': 'y' if len(game_data['teams'].get(game_data['metadata']['away'], {}).get('players', [])) >= 9 else 'n',
        'box': 'y' if len(game_data['teams'].get(game_data['metadata']['away'], {}).get('players', [])) >= 9 else 'n',
        'php': '',
        'season': game_data['metadata']['date'][:4],
        'source': game_data['metadata']['source'],
        'status': game_data['metadata']['status'],
        'status-reason': game_data['metadata']['status-reason'],
        'forfeit': game_data['metadata'].get('forfeit', '')
    }

    # Robust vruns/hruns derivation (line_scores preferred, totals fallback)
    away = game_data['metadata']['away']
    home = game_data['metadata']['home']

    def get_runs(team):
        if game_data.get('line_scores') and team in game_data['line_scores']:
            return game_data['line_scores'][team].get('runs', 0)
        team_data = game_data['teams'].get(team) or {}
        if isinstance(team_data, dict):
            totals = team_data.get('totals') or {}
            if isinstance(totals, dict):
                return totals.get('r', 0)
        return 0

    gameinfo['vruns'] = get_runs(away)
    gameinfo['hruns'] = get_runs(home)

    if not game_data['metadata']['away'] or not game_data['metadata']['home']:
        logging.error(f"[gid={gid}] Missing away or home team metadata, skipping winner/loser determination")
        return
    if not game_data['teams'] and game_data['metadata']['status'].lower() not in ['postponed', 'abandoned', 'other']:
        logging.error(f"[gid={gid}] No teams initialized, skipping CSV writing")
        return
    for team in [game_data['metadata']['away'], game_data['metadata']['home']]:
        game_data['teams'][team] = game_data['teams'].get(team, {'players': [], 'totals': None})
    if gameinfo['vruns'] > gameinfo['hruns']:
        gameinfo['wteam'] = gameinfo['visteam']
        gameinfo['lteam'] = gameinfo['hometeam']
    elif gameinfo['hruns'] > gameinfo['vruns']:
        gameinfo['wteam'] = gameinfo['hometeam']
        gameinfo['lteam'] = gameinfo['visteam']

    try:
        batting_data = []
        pitching_data = []
        fielding_data = []
        teamstats_data = []
        pitcher_seq = {team: 1 for team in game_data['teams']}
        defensive_positions = ['p', 'c', '1b', '2b', '3b', 'ss', 'lf', 'cf', 'rf']
        doubles_allowed = {team: 0 for team in game_data['teams']}
        triples_allowed = {team: 0 for team in game_data['teams']}
        hr_allowed = {team: 0 for team in game_data['teams']}
        sh_allowed = {team: 0 for team in game_data['teams']}
        sf_allowed = {team: 0 for team in game_data['teams']}
        sb_allowed = {team: 0 for team in game_data['teams']}

        pitchers_per_team = {team: [] for team in game_data['teams']}
        catchers_per_team = {team: [] for team in game_data['teams']}
        for team, data in game_data['teams'].items():
            for player in data['players']:
                #fix
                if isinstance(player, dict) and player.get('position') and re.match(r'^(p|p-.*|.*-p)$', str(player.get('position', ''))):
                    pitchers_per_team[team].append(player['player_id'])
                    player['is_pitcher'] = True
                if 'c' in player['position'].split('-'):
                    catchers_per_team[team].append(player['player_id'])

        away_team = game_data['metadata']['away']
        home_team = game_data['metadata']['home']
        gameinfo['batteries'] = 'y' if (len(pitchers_per_team.get(away_team, [])) >= 1 and 
                                        len(catchers_per_team.get(away_team, [])) >= 1 and 
                                        len(pitchers_per_team.get(home_team, [])) >= 1 and 
                                        len(catchers_per_team.get(home_team, [])) >= 1) else 'n'

        # First pass: Populate batting_data and pitching_data
        for bstat in game_data['batting_stats']:
            team = bstat['team']
            opponent = game_data['metadata']['home'] if team == game_data['metadata']['away'] else game_data['metadata']['away']
            stat = bstat['stat']
            count = bstat['count']
            if stat in ['2B', 'D']:
                doubles_allowed[opponent] += count
            elif stat in ['3B', 'T']:
                triples_allowed[opponent] += count
            elif stat == 'HR':
                hr_allowed[opponent] += count
            elif stat == 'SH':
                sh_allowed[opponent] += count
            elif stat == 'SF':
                sf_allowed[opponent] += count
            elif stat == 'SB':
                sb_allowed[opponent] += count

        for team, data in game_data['teams'].items():
            opponent = game_data['metadata']['home'] if team == game_data['metadata']['away'] else game_data['metadata']['away']
            team_po = data.get('totals', {}).get('po', 0) if data.get('totals') is not None else 0
            for player in data['players']:
                batting = {
                    'gid': gid,
                    'id': player['player_id'],
                    'team': team_abbr.get(team, team),
                    'b_lp': '' if team in incomplete_lineups else player['b_lp'],
                    'b_seq': player['b_seq'],
                    'stattype': 'value',
                    'b_pa': '',
                    # fix
                    'b_ab': safe_val(player.get('ab')),
                    'b_r': safe_val(player.get('r')),
                    'b_h': safe_val(player.get('h')),
                    'b_d': 0,
                    'b_t': 0,
                    'b_hr': 0,
                    'b_rbi': safe_val(player.get('rbi')),
                    'b_sh': 0,
                    'b_sf': 0,
                    'b_hbp': 0,
                    'b_w': '',
                    'b_iw': '',
                    'b_k': '',
                    'b_sb': 0,
                    'b_cs': '',
                    'b_gdp': '',
                    'b_xi': '',
                    'b_roe': 0,
                    'dh': '1' if 'dh' in player['position'].split('-') else '',
                    # ph correction
                    'ph': '1' if 'ph' in player['position'].split('-') else '',
                    'pr': '',
                    'date': gameinfo['date'],
                    'number': gameinfo['number'],
                    'site': gameinfo['site'],
                    'vishome': 'v' if team == game_data['metadata']['away'] else 'h',
                    'opp': team_abbr.get(opponent, opponent),
                    'win': '1' if gameinfo['wteam'] == team_abbr.get(team, team) else '',
                    'loss': '1' if gameinfo['lteam'] == team_abbr.get(team, team) else '',
                    'tie': '1' if gameinfo['vruns'] == gameinfo['hruns'] else '',
                    'gametype': gameinfo['gametype'],
                    'box': gameinfo['box'],
                    'pbp': '',
                    'source': gameinfo['source']
                }
                batting_data.append(batting)
                if re.match(r'^(p|p-.*|.*-p)$', player['position']):
                    p_d_val = doubles_allowed[team] if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_t_val = triples_allowed[team] if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_hr_val = hr_allowed[team] if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_sh_val = sh_allowed[team] if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_sf_val = sf_allowed[team] if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_sb_val = sb_allowed[team] if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_cs_val = ''
                    p_pb_val = sum(f.get('d_pb', 0) for f in fielding_data if f.get('team') == team_abbr.get(opponent, opponent)) if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else ''
                    p_r_val = ''
                    if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team]:
                        p_r_val = gameinfo['hruns'] if team == game_data['metadata']['away'] else gameinfo['vruns']
                    else:
                        for pstat in game_data['pitching_stats']:
                            if pstat['player_id'] == player['player_id'] and pstat['team'] == team and pstat['stat'] == 'R':
                                p_r_val = pstat['count']
                                break
                    wp_val = ''
                    lp_val = ''
                    save_val = ''
                    gf_val = ''
                    if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team]:
                        gs_val = '1'
                        team_runs = gameinfo['vruns'] if team == game_data['metadata']['away'] else gameinfo['hruns']
                        opp_runs = gameinfo['hruns'] if team == game_data['metadata']['away'] else gameinfo['vruns']
                        if team_runs > opp_runs:
                            wp_val = '1'
                        elif team_runs < opp_runs:
                            lp_val = '1'
                    else:
                        gs_val = '1' if pitcher_seq[team] == 1 else ''
                    for pstat in game_data['pitching_stats']:
                        if pstat['player_id'] == player['player_id'] and pstat['team'] == team:
                            if pstat['stat'] == 'W':
                                wp_val = '1'
                            elif pstat['stat'] == 'L':
                                lp_val = '1'
                            elif pstat['stat'] == 'SV':
                                save_val = '1'
                            elif pstat['stat'] == 'GF':
                                gf_val = '1'
                            elif pstat['stat'] == 'GS':
                                gs_val = '1'
                    pitching = {
                        'gid': gid,
                        'id': player['player_id'],
                        'team': team_abbr.get(team, team),
                        'p_seq': pitcher_seq[team],
                        'stattype': 'value',
                        'p_ipouts': 0,
                        'p_noout': '',
                        'p_bfp': '',
                        'p_h': '',
                        'p_d': p_d_val,
                        'p_t': p_t_val,
                        'p_hr': p_hr_val,
                        'p_r': p_r_val,
                        'p_er': 0,
                        'p_w': 0,
                        'p_iw': '',
                        'p_k': 0,
                        'p_hbp': 0,
                        'p_wp': 0,
                        'p_bk': 0,
                        'p_sh': p_sh_val,
                        'p_sf': p_sf_val,
                        'p_sb': p_sb_val,
                        'p_cs': p_cs_val,
                        'p_pb': p_pb_val,
                        'wp': wp_val,
                        'lp': lp_val,
                        'save': save_val,
                        'gs': gs_val,
                        'gf': gf_val,
                        'cg': '1' if len(pitchers_per_team[team]) == 1 and player['player_id'] in pitchers_per_team[team] else '',
                        'date': gameinfo['date'],
                        'number': gameinfo['number'],
                        'site': gameinfo['site'],
                        'vishome': 'v' if team == game_data['metadata']['away'] else 'h',
                        'opp': team_abbr.get(opponent, opponent),
                        'win': wp_val,
                        'loss': lp_val,
                        'tie': '1' if gameinfo['vruns'] == gameinfo['hruns'] else '',
                        'gametype': gameinfo['gametype'],
                        'box': gameinfo['box'],
                        'pbp': '',
                        'source': gameinfo['source']
                    }
                    pitcher_seq[team] += 1
                    pitching_data.append(pitching)

        for stat in game_data['batting_stats']:
            for b in batting_data:
                if b['id'] == stat['player_id'] and b.get('team') == team_abbr.get(stat['team'], stat['team']):
                    if stat['stat'] in ['2B', 'D']:
                        b['b_d'] = stat['count']
                    elif stat['stat'] in ['3B', 'T']:
                        b['b_t'] = stat['count']
                    elif stat['stat'] == 'HR':
                        b['b_hr'] = stat['count']
                    elif stat['stat'] == 'SB':
                        b['b_sb'] = stat['count']
                    elif stat['stat'] == 'SH':
                        b['b_sh'] = stat['count']
                    elif stat['stat'] == 'SF':
                        b['b_sf'] = stat['count']
                    elif stat['stat'] == 'HP':
                        b['b_hbp'] = stat['count']
                    # elif stat['stat'] == 'ROE':
                        # b['b_roe'] = stat['count']

        for stat in game_data['pitching_stats']:
            for p in pitching_data:
                if p['id'] == stat['player_id'] and p.get('team') == team_abbr.get(stat['team'], stat['team']):
                    if stat['stat'] == 'IP':
                        p['p_ipouts'] = stat['count']
                    elif stat['stat'] == 'H':
                        p['p_h'] = stat['count']
                    elif stat['stat'] == 'BB':
                        p['p_w'] = stat['count']
                    elif stat['stat'] == 'SO':
                        p['p_k'] = stat['count']
                    elif stat['stat'] == 'HP':
                        p['p_hbp'] = stat['count']
                    elif stat['stat'] == 'WP':
                        p['p_wp'] = stat['count']
                    elif stat['stat'] == 'BK':
                        p['p_bk'] = stat['count']
                    elif stat['stat'] == 'ER':
                        p['p_er'] = stat['count']

        # Fallback for p_ipouts in minimal RHE (last resort per user request):
        # Only if no explicit P_IP was given (p_ipouts still 0) AND sole pitcher.
        # Exception: if no innings evidence in line score (derived == ''), set '' for ALL pitchers
        # (as in test_R_LineScoreTotalsOnly.txt where # innings unknown).
        for team in list(game_data['teams'].keys()):
            derived = get_defensive_outs(team, game_data)
            if len(pitchers_per_team.get(team, [])) == 1 or derived == '':
                for p in pitching_data:
                    if p.get('team') == team_abbr.get(team, team) and p.get('p_ipouts', 0) == 0:
                        p['p_ipouts'] = derived
                        if len(pitchers_per_team.get(team, [])) == 1:
                            break

        # Second pass: Populate fielding_data using completed batting_data and pitching_data
        for team, data in game_data['teams'].items():
            opponent = game_data['metadata']['home'] if team == game_data['metadata']['away'] else game_data['metadata']['away']
            team_po = data.get('totals', {}).get('po', 0) if data.get('totals') is not None else 0
            for player in data['players']:
                d_seq = player['seq']
                positions = player['position'].split('-')
                d_pos = positions[0] if positions else ''
                # Calculate d_ifouts: for non-pitchers, use TOTALS po adjusted by B_XO if only player at position; for pitchers, use p_ipouts; else ''
                d_ifouts = ''
                if player.get('is_pitcher', False) and len(pitchers_per_team[team]) == 1:
                    for p in pitching_data:
                        if p['id'] == player['player_id'] and p['team'] == team_abbr.get(team, team):
                            d_ifouts = p.get('p_ipouts', '')
                            break
                else:
                    position_players = [p for p in data['players'] if p['position'].split('-')[0] == d_pos]
                    if len(position_players) == 1 and d_pos in defensive_positions:
                        # Last resort (user request): use line-score derived defensive outs ONLY if team_po not given in TOTALS
                        # (so team_po + B_XO cannot be derived). In full boxes with po in TOTALS, keep explicit path.
                        totals = data.get('totals') or {}
                        if 'po' not in totals or totals.get('po') is None:
                            d_ifouts = get_defensive_outs(team, game_data)
                        else:
                            d_ifouts = team_po
                            for bstat in game_data['batting_stats']:
                                if bstat['stat'] == 'XO' and player_team.get(bstat['player_id']) == opponent:
                                    d_ifouts += bstat['count']
                # Calculate d_wp and d_sb: only for sole catcher
                d_wp_val = sum(p.get('p_wp', 0) for p in pitching_data if p.get('team') == team_abbr.get(team, team)) if 'c' in player['position'].split('-') and len(catchers_per_team[team]) == 1 else ''
                d_sb_val = sum(b.get('b_sb', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)) if 'c' in player['position'].split('-') and len(catchers_per_team[team]) == 1 else ''
                fielding = {
                    'gid': gid,
                    'id': player['player_id'],
                    'team': team_abbr.get(team, team),
                    'd_seq': d_seq,
                    'd_pos': player['position'],
                    'stattype': 'value',
                    'd_ifouts': d_ifouts,
                    'd_po': safe_val(player.get('po')),
                    'd_a': safe_val(player.get('a')),
                    'd_e': safe_val(player.get('e')),
                    'd_dp': 0,
                    'd_tp': 0,
                    'd_pb': 0,
                    'd_wp': d_wp_val,
                    'd_sb': d_sb_val,
                    'd_cs': '',
                    'd_gs': '1' if player['seq'] == 1 else '',
                    'date': gameinfo['date'],
                    'number': gameinfo['number'],
                    'site': gameinfo['site'],
                    'vishome': 'v' if team == game_data['metadata']['away'] else 'h',
                    'opp': team_abbr.get(opponent, opponent),
                    'win': '1' if gameinfo['wteam'] == team_abbr.get(team, team) else '',
                    'loss': '1' if gameinfo['lteam'] == team_abbr.get(team, team) else '',
                    'tie': '1' if gameinfo['vruns'] == gameinfo['hruns'] else '',
                    'gametype': gameinfo['gametype'],
                    'box': gameinfo['box'],
                    'pbp': '',
                    'source': gameinfo['source']
                }
                fielding_data.append(fielding)

        for stat in game_data['fielding_stats']:
            for f in fielding_data:
                if f['id'] == stat['player_id'] and f.get('team') == team_abbr.get(stat['team'], stat['team']):
                    if stat['stat'] == 'PB':
                        f['d_pb'] = stat['count']
                    if stat['stat'] == 'DP':
                        f['d_dp'] = stat['count']
                    elif stat['stat'] == 'TP':
                        f['d_tp'] = stat['count']

        for p in pitching_data:
            if p['wp'] == '1':
                gameinfo['wp'] = p['id']
            if p['lp'] == '1':
                gameinfo['lp'] = p['id']
            if p['save'] == '1':
                gameinfo['save'] = p['id']

        # Assign individual d_dp from dp_counts
        for (player_id, team, stat), count in dp_counts.items():
            if stat == 'DP':
                for f in fielding_data:
                    if f['id'] == player_id and f.get('team') == team_abbr.get(team, team):
                        f['d_dp'] = count

        for team in game_data['teams']:
            opponent = game_data['metadata']['home'] if team == game_data['metadata']['away'] else game_data['metadata']['away']
            data = game_data['teams'].get(team, {'players': [], 'totals': None})
            if data is None or data.get('totals') is None:
                data = {'players': [], 'totals': {}}
            team_po = data.get('totals', {}).get('po', 0) if data.get('totals') is not None else 0
            # Safe inning-by-inning data
            line_score = game_data.get('line_scores', {}).get(team, {}) or {}
            innings = line_score.get('innings', []) if isinstance(line_score, dict) else []
            innings_dict = {f'inn{i + 1}': innings[i] if i < len(innings) else '' for i in range(28)}
            team_stats = {
                'gid': gid,
                'team': team_abbr.get(team, team),
                **innings_dict,
                # add team data lob roe er
                'lob': game_data['teams'].get(team, {}).get('team_events', {}).get('lob', ''),
                'b_roe': game_data['teams'].get(team, {}).get('team_events', {}).get('roe', ''),
                'b_er': game_data['teams'].get(team, {}).get('team_events', {}).get('er', ''),
                'mgr': '',
                'stattype': 'default',
                'b_pa': '',
                # 'b_ab': data.get('totals', {}).get('ab', 0) if data.get('totals') is not None else sum(b.get('b_ab', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_ab': safe_val(data.get('totals', {}).get('ab')),
                'b_r': game_data['line_scores'].get(team, {}).get('runs', data.get('totals', {}).get('r', '') if data.get('totals') is not None else ''),
                # 'b_h': data.get('totals', {}).get('h', 0) if data.get('totals') is not None else sum(b.get('b_h', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_h': safe_val(data.get('totals', {}).get('h')),
                'b_d': sum(b.get('b_d', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_t': sum(b.get('b_t', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_hr': sum(b.get('b_hr', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                # 'b_rbi': data.get('totals', {}).get('rbi', 0) if data.get('totals') is not None else sum(b.get('b_rbi', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_rbi': safe_val(data.get('totals', {}).get('rbi')),
                'b_sh': sum(b.get('b_sh', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_sf': sum(b.get('b_sf', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_hbp': sum(b.get('b_hbp', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_w': sum(p.get('p_w', 0) for p in pitching_data if p.get('team') == team_abbr.get(opponent, opponent)),
                'b_iw': '',
                'b_k': sum(p.get('p_k', 0) for p in pitching_data if p.get('team') == team_abbr.get(opponent, opponent)),
                'b_sb': sum(b.get('b_sb', 0) for b in batting_data if b.get('team') == team_abbr.get(team, team)),
                'b_cs': '',
                'b_gdp': '',
                'b_xi': '',
                # 'b_roe': sum(bstat['count'] for bstat in game_data['batting_stats'] if bstat['team'] == team and bstat['stat'] == 'ROE'),
                # Last resort (user request): use derived defensive outs if team_po not given in TOTALS (minimal RHE)
                'p_ipouts': get_defensive_outs(team, game_data) if ('po' not in (data.get('totals') or {}) or data.get('totals', {}).get('po') is None) else team_po,
                'p_noout': '',
                'p_bfp': '',
                # Fix for p_h
                'p_h': ((game_data['teams'].get(opponent, {}) or {}).get('totals') or {}).get('h', 0) if isinstance(
                    ((game_data['teams'].get(opponent, {}) or {}).get('totals') or {}), dict) else sum(
                    b.get('b_h', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),

                'p_d': sum(b.get('b_d', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'p_t': sum(b.get('b_t', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'p_hr': sum(b.get('b_hr', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                # fix for p_r
                'p_r': (game_data['line_scores'].get(opponent) or {}).get('runs') if (
                    game_data['line_scores'].get(opponent) or {}) else (
                    (game_data['teams'].get(opponent, {}) or {}).get('totals') or {}).get('r', 0) if isinstance(
                    ((game_data['teams'].get(opponent, {}) or {}).get('totals') or {}), dict) else 0,
                'p_er': '',
                'p_w': sum(p.get('p_w', 0) for p in pitching_data if p.get('team') == team_abbr.get(team, team)),
                'p_iw': '',
                'p_k': sum(p.get('p_k', 0) for p in pitching_data if p.get('team') == team_abbr.get(team, team)),
                'p_hbp': sum(b.get('b_hbp', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'p_wp': sum(p.get('p_wp', 0) for p in pitching_data if p.get('team') == team_abbr.get(team, team)),
                'p_bk': sum(p.get('p_bk', 0) for p in pitching_data if p.get('team') == team_abbr.get(team, team)),
                'p_sh': sum(b.get('b_sh', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'p_sf': sum(b.get('b_sf', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'p_sb': sum(b.get('b_sb', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'p_cs': '',
                'p_pb': sum(f.get('d_pb', 0) for f in fielding_data if f.get('team') == team_abbr.get(team, team)),
                'd_po': team_po,
                #'d_a': data.get('totals', {}).get('a', 0) if data.get('totals') is not None else 0,
                'd_a': safe_val(data.get('totals', {}).get('a')),
                #'d_e': data.get('totals', {}).get('e', 0) if data.get('totals') is not None else 0,
                'd_e': safe_val(data.get('totals', {}).get('e')),
                'd_dp': len(set([e for e in dp_events.get(team, []) if e.startswith(f"{team}_F_DP_")])),
                'd_tp': len(set([e for e in dp_events.get(team, []) if e.startswith(f"{team}_F_TP_")])),
                'd_pb': sum(f.get('d_pb', 0) for f in fielding_data if f.get('team') == team_abbr.get(team, team)),
                'd_wp': sum(p.get('p_wp', 0) for p in pitching_data if p.get('team') == team_abbr.get(team, team)),
                'd_sb': sum(b.get('b_sb', 0) for b in batting_data if b.get('team') == team_abbr.get(opponent, opponent)),
                'd_cs': '',
                #fix
                'start_l1': lineup_positions.get(team, {}).get(1, {}).get(1, ''),
                'start_l2': lineup_positions.get(team, {}).get(2, {}).get(1, ''),
                'start_l3': lineup_positions.get(team, {}).get(3, {}).get(1, ''),
                'start_l4': lineup_positions.get(team, {}).get(4, {}).get(1, ''),
                'start_l5': lineup_positions.get(team, {}).get(5, {}).get(1, ''),
                'start_l6': lineup_positions.get(team, {}).get(6, {}).get(1, ''),
                'start_l7': lineup_positions.get(team, {}).get(7, {}).get(1, ''),
                'start_l8': lineup_positions.get(team, {}).get(8, {}).get(1, ''),
                'start_l9': lineup_positions.get(team, {}).get(9, {}).get(1, ''),
                #end fix
                'start_f1': '',
                'start_f2': '',
                'start_f3': '',
                'start_f4': '',
                'start_f5': '',
                'start_f6': '',
                'start_f7': '',
                'start_f8': '',
                'start_f9': '',
                'start_f10': '',
                'date': gameinfo['date'],
                'number': gameinfo['number'],
                'site': gameinfo['site'],
                'vishome': 'v' if team == game_data['metadata']['away'] else 'h',
                'opp': team_abbr.get(opponent, opponent),
                'win': '1' if gameinfo['wteam'] == team_abbr.get(team, team) else '',
                'loss': '1' if gameinfo['lteam'] == team_abbr.get(team, team) else '',
                'tie': '1' if gameinfo['vruns'] == gameinfo['hruns'] else '',
                'gametype': gameinfo['gametype'],
                'box': gameinfo['box'],
                'pbp': '',
                'source': gameinfo['source']
            }
            position_map = {'p': 'start_f1', 'c': 'start_f2', '1b': 'start_f3', '2b': 'start_f4', '3b': 'start_f5',
                            'ss': 'start_f6', 'lf': 'start_f7', 'cf': 'start_f8', 'rf': 'start_f9', 'dh': 'start_f10'}
            for player in data['players']:
                if player['seq'] == 1:
                    positions = player['position'].split('-')
                    for pos in positions:
                        if pos in position_map:
                            team_stats[position_map[pos]] = player['player_id']
            for bstat in game_data['batting_stats']:
                if bstat['team'] == team and bstat['stat'] == 'LOB':
                    team_stats['lob'] = bstat['count']
                if bstat['team'] == team and bstat['stat'] == 'ROE':
                    team_stats['b_roe'] = bstat['count']
            for bstat in game_data['batting_stats']:
                if bstat['stat'] == 'XO' and player_team.get(bstat['player_id']) == opponent:
                    team_stats['p_ipouts'] += bstat['count']
                    team_stats['d_po'] += bstat['count']
            teamstats_data.append(team_stats)

        # Write gameinfo.csv
        with open(os.path.join(output_dir, 'gameinfo.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=GAMEINFO_FIELDNAMES)
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(gameinfo)

        # Write batting.csv
        with open(os.path.join(output_dir, 'batting.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'gid', 'id', 'team', 'b_lp', 'b_seq', 'stattype', 'b_pa', 'b_ab', 'b_r', 'b_h', 'b_d', 'b_t',
                'b_hr', 'b_rbi', 'b_sh', 'b_sf', 'b_hbp', 'b_w', 'b_iw', 'b_k', 'b_sb', 'b_cs',
                'b_gdp', 'b_xi', 'b_roe', 'dh', 'ph', 'pr', 'date', 'number', 'site', 'vishome',
                'opp', 'win', 'loss', 'tie', 'gametype', 'box', 'pbp', 'source'
            ])
            if f.tell() == 0:
                writer.writeheader()
            for row in batting_data:
                writer.writerow(row)

        # Write pitching.csv
        with open(os.path.join(output_dir, 'pitching.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'gid', 'id', 'team', 'p_seq', 'stattype', 'p_ipouts', 'p_noout', 'p_bfp', 'p_h', 'p_d',
                'p_t', 'p_hr', 'p_r', 'p_er', 'p_w', 'p_iw', 'p_k', 'p_hbp', 'p_wp', 'p_bk', 'p_sh',
                'p_sf', 'p_sb', 'p_cs', 'p_pb', 'wp', 'lp', 'save', 'gs', 'gf', 'cg', 'date',
                'number', 'site', 'vishome', 'opp', 'win', 'loss', 'tie', 'gametype', 'box', 'pbp', 'source'
            ])
            if f.tell() == 0:
                writer.writeheader()
            for row in pitching_data:
                writer.writerow(row)

        # Write fielding.csv
        with open(os.path.join(output_dir, 'fielding.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'gid', 'id', 'team', 'd_seq', 'd_pos', 'stattype', 'd_ifouts', 'd_po', 'd_a', 'd_e',
                'd_dp', 'd_tp', 'd_pb', 'd_wp', 'd_sb', 'd_cs', 'd_gs', 'date', 'number', 'site',
                'vishome', 'opp', 'win', 'loss', 'tie', 'gametype', 'box', 'pbp', 'source'
            ])
            if f.tell() == 0:
                writer.writeheader()
            for row in fielding_data:
                writer.writerow(row)

        # Write discrepancies.csv
        with open(os.path.join(output_dir, 'discrepancies.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['gid', 'team', 'discrepancy'])
            if f.tell() == 0:
                writer.writeheader()
            for d in game_data['discrepancies']:
                writer.writerow(d)

        # Write notes.csv
        with open(os.path.join(output_dir, 'notes.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['gid', 'text'])
            if f.tell() == 0:
                writer.writeheader()
            for note in game_data['notes']:
                writer.writerow(note)

        # Write teamstats.csv
        with open(os.path.join(output_dir, 'teamstats.csv'), 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=TEAMSTATS_FIELDNAMES)
            if f.tell() == 0:
                writer.writeheader()
            for row in teamstats_data:
                writer.writerow(row)
    except Exception as e:
        logging.error(f"[gid={gid}] Error in teamstats processing: {e}")
        # Non-fatal for postponed games with no play data
        pass

def main():
    config = setup_config()
    team_abbr = load_team_abbreviations(config['team_abbreviations'])
    boxscore_folder = config['boxscore_folder']
    for filename in os.listdir(boxscore_folder):
        if filename.endswith('.txt'):
            try:
                with open(os.path.join(boxscore_folder, filename), 'r', encoding='utf-8') as f:
                    content = f.read()
                    boxscores = content.split('\n---\n')
                    for boxscore_text in boxscores:
                        boxscore_text = boxscore_text.strip()
                        if not boxscore_text:
                            continue
                        game_data, gid, lineup_positions, dp_counts, player_team, incomplete_lineups, dp_events = parse_boxscore(boxscore_text, team_abbr)
                        if game_data:
                            write_csvs(game_data, gid, lineup_positions, team_abbr, config['output_dir'], dp_counts, player_team, incomplete_lineups, dp_events)
            except Exception as e:
                logging.error(f"Error processing file {filename}: {e}")

if __name__ == "__main__":
    main()