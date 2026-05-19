# Technical Specification: Baseball Boxscore Parser (Updated May 2026)

## 1. Architecture
- Standalone Python script: `extract_boxscores.py`
- Core functions: `parse_boxscore()`, `write_csvs()`, `main()`, plus helpers (`get_defensive_outs()`, `create_minimal_gameinfo_row()`, `safe_val()` patterns, etc.).
- Configuration-driven via `config.ini` and `team_abbreviations.csv`.
- Dependencies: Only Python 3 standard libraries (`os`, `re`, `csv`, `configparser`, `datetime`, `logging`).
- Output: Retrosheet-inspired CSV files for analysis.

## 2. Data Structures
- `game_data`: Central dict containing:
  - `metadata`: Game-level info (date, teams, source, status, status-reason, forfeit, forfeit-to, wteam, lteam, umpires, etc.)
  - `teams`: Dict of team → {players: list, totals: dict or None}
  - `line_scores`: Inning-by-inning runs
  - `batting_stats`, `pitching_stats`, `fielding_stats`, `discrepancies`, `notes`
- `player_team`: Maps standardized playerID → team
- `lineup_positions`, `dp_events`, `pitchers_per_team`, `catchers_per_team`

## 3. Key Algorithms & Logic

### 3.1 parse_boxscore()
- Two-pass parsing over the boxscore text.
- **Metadata pass**: Parses `key: value` lines (including new `status:`, `forfeit-to:`, `status-reason:`).
- **Main pass**: Parses team headers, player lines, TOTALS, events (B_*, P_*, F_*), and line scores.
- Robust header detection supporting many variants (AB R H PO A E, R H E, R only, etc.).
- Handles `'x'` / `'X'` as missing/zero values.
- Flags incomplete lineups (max_lp < 9 or gaps).
- Derives defensive outs (`get_defensive_outs()`) as last resort when P_IP / team PO not present.
- Validates player sums vs TOTALS; logs discrepancies.

### 3.2 Special Status Handling (Postponed & Forfeits)
- **Postponed / Abandoned / Other**:
  - Early exit in `write_csvs()` when `status` is one of these.
  - Writes **only** `gameinfo.csv` with `status` and `status-reason`.
  - No `teamstats.csv`, batting, pitching, or fielding output.
- **Forfeits** (`status: forfeit`):
  - **Type 1 (Pre-game)**: No player data. Early exit writes minimal `gameinfo.csv` (`forfeit='Y'`, `wteam`/`lteam` from `forfeit-to:`) + minimal `teamstats.csv` (only win/loss + identifiers).
  - **Type 2 (Post-official)**: Full box score parsed normally; `forfeit='Y'` added to `gameinfo.csv`.
  - `forfeit-to: home|away` determines winner/loser.

### 3.3 write_csvs()
- Normal path: Builds full `gameinfo`, batting, pitching, fielding, and teamstats rows.
- Uses centralized `GAMEINFO_FIELDNAMES` and `TEAMSTATS_FIELDNAMES` constants.
- Special early-exit paths for postponed and Type 1 forfeits (uses `create_minimal_gameinfo_row()` helper).
- Safe handling of `None` totals via guards and `safe_val()`-style patterns.

### 3.4 Standardization & Helpers
- Player ID standardization (lastname + initial + optional disambiguator).
- IP conversion to outs.
- Defensive outs derivation from line score when explicit data missing.
- Win/Loss assignment logic updated for forfeit-to.

### 3.5 Error Handling & Validation
- Non-fatal error handling for edge cases (postponed/forfeit with no teams).
- Discrepancy logging between player sums and TOTALS.
- Warnings for missing data, invalid formats.

## 4. Configuration
- `config.ini`: boxscore_folder, output_dir, team_abbreviations path.
- `team_abbreviations.csv`: team_name → abbreviation mapping.

## 5. Output Files
- `gameinfo.csv` — Core game metadata + `status`, `status-reason`, `forfeit`, `wteam`, `lteam`.
- `batting.csv`, `pitching.csv`, `fielding.csv` — Player-level stats.
- `teamstats.csv` — Team-level aggregated stats (including minimal rows for Type 1 forfeits).
- `discrepancies.csv` — Validation mismatches.
- `notes.csv` — Notes and recaps (used less now for special statuses).

## 6. Testing & Validation Notes
- Successfully handles:
  - Full/maximum box scores
  - Minimal formats (RHE, R-only, no line score, 'x' stats)
  - Postponed games
  - Both types of forfeits
  - Full season runs (60+ games/team) with zero fatal errors
- Strong emphasis on robustness for historical newspaper transcriptions.

## 7. Recent Major Changes (since original spec)
- Added full support for `status` and `forfeit-to` conventions.
- Introduced early-exit logic for postponed and pre-game forfeit cases.
- Centralized fieldnames constants and helper functions for maintainability.
- Hardened handling of missing/None data and minimal box scores.
- Created companion `README.md` documenting supported formats and conventions.

---

*This specification reflects the state of the parser as of May 2026.*