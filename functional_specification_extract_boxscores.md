# Functional Specification: Baseball Boxscore Parser

**Version:** Updated May 2026  
**Script:** `extract_boxscores.py`

## 1. Purpose

The `extract_boxscores.py` script parses historical baseball box score text files (primarily early 20th-century newspaper formats) and converts them into structured, Retrosheet-inspired CSV files suitable for analysis. It is designed to handle both richly detailed ("maximum") box scores and highly minimal formats while maintaining data integrity through validation and discrepancy logging.

## 2. Scope

- **Input**: One or more box scores per text file, separated by `---`.
- **Output**: Seven CSV files (`gameinfo.csv`, `batting.csv`, `pitching.csv`, `fielding.csv`, `teamstats.csv`, `discrepancies.csv`, `notes.csv`).
- Supports regular games, incomplete lineups, minimal RHE / R-only / no-line-score formats, postponed games, and both pre-game and post-official forfeits.
- Standardizes player names via `playerID`, validates player sums against team totals, and gracefully handles missing or non-numeric values (`x`, blank, etc.).

## 3. Functional Requirements

### 3.1 Input Processing

- Reads box score files from the folder specified in `config.ini`.
- Parses metadata lines: `date`, `number`, `league`, `away`/`home`, `source`, `site`, `attendance`, `time`, `umpires`, `gametype`, `batted-first`, `outsatend`, `status`, `status-reason`, and `forfeit-to`.
- Parses team headers (e.g., `AB R H PO A E`, `R H E`, `R`, etc.).
- Parses player lines in the format `lineup_pos playerID @ position: stats...`
- Parses `TOTALS` lines for team totals.
- Parses batting/pitching/fielding events (`B_*`, `P_*`, `F_*`).
- Parses line scores (`line: Team: inn1 inn2 ... - runs`).
- Parses notes and recaps.

### 3.2 Data Standardization & Robustness

- Converts player names to `playerID` format (lastname + initial + optional disambiguator).
- Treats `x` / `X` and blank values as missing (0 or NULL depending on context).
- Uses defensive fallback logic (`get_defensive_outs()`) to derive `p_ipouts` / `d_ifouts` from line scores when explicit data is absent (last resort only).
- Flags incomplete lineups and sets `lineups = 'n'` in `gameinfo.csv`.

### 3.3 Validation

- Sums player statistics and compares them to reported `TOTALS`.
- Logs discrepancies to `discrepancies.csv`.
- Warns on suspicious values (e.g., stats ≥ 100) or missing key fields.

### 3.4 Special Status Handling (Updated Behavior)

The script now cleanly supports games that did not play to completion:

- **Postponed / Abandoned / Other** (`status: postponed`, etc.)
  - Writes a row to `gameinfo.csv` with `status` and `status-reason` populated.
  - Does **not** write to `batting.csv`, `pitching.csv`, `fielding.csv`, or normal `teamstats.csv`.
  - No entry is written to `notes.csv` for these games.

- **Forfeits – Type 1 (Pre-game / before becoming official)**
  - Identified by `status: forfeit` + `forfeit-to: home|away`.
  - Writes to `gameinfo.csv` with `forfeit = 'Y'`, `wteam`, and `lteam`.
  - Writes a **minimal** row to `teamstats.csv` containing only `win`/`loss` flags (plus basic identifiers).
  - Does **not** write player-level batting/pitching/fielding rows.

- **Forfeits – Type 2 (After the game became official)**
  - A normal box score exists.
  - Parsed normally with full output to all CSVs.
  - `forfeit = 'Y'` is set in `gameinfo.csv`.

### 3.5 Output Files

| File            | Contents                                      | Notes |
|-----------------|-----------------------------------------------|-------|
| `gameinfo.csv`  | Game-level metadata + `status`, `forfeit`, `wteam`/`lteam` | Always written |
| `batting.csv`   | Individual batter lines                       | Skipped for Type 1 forfeits & postponed |
| `pitching.csv`  | Individual pitcher lines                      | Skipped for Type 1 forfeits & postponed |
| `fielding.csv`  | Individual fielder lines                      | Skipped for Type 1 forfeits & postponed |
| `teamstats.csv` | Team-level stats + inning-by-inning runs     | Minimal rows only for Type 1 forfeits |
| `discrepancies.csv` | Player-sum vs TOTALS mismatches            | Always generated when discrepancies exist |
| `notes.csv`     | Notes and recaps                              | Rarely used after special-status changes |

### 3.6 Configuration

- `config.ini`: `boxscore_folder`, `output_dir`
- `team_abbreviations.csv`: team name → abbreviation mapping (required for consistent `visteam`/`hometeam` and `wteam`/`lteam` values)

## 4. Non-Functional Requirements

- **Error Handling**: Logs warnings/errors but continues processing subsequent box scores.
- **Robustness**: Designed to handle missing data, non-standard headers, and minimal formats without crashing.
- **Logging**: Warning level by default; debug mode available via command-line flag.
- **Dependencies**: Standard library only (`os`, `re`, `csv`, `configparser`, `datetime`, `logging`).

## 5. Assumptions

- Input files are UTF-8 encoded.
- Box scores within a file are separated by `---`.
- Team name abbreviations are provided via `team_abbreviations.csv`.
- The transcriber provides complete `TOTALS` lines (no `x` in key totals) for best results.
- No internet access or external package installation is required.

## 6. Recent Major Changes (Since Original Spec)

- Postponed and pre-game forfeit games now write to `gameinfo.csv` (and minimal `teamstats.csv` for forfeits) instead of being skipped or routed only to `notes.csv`.
- Added explicit `status`, `forfeit`, and `forfeit-to` parsing and output.
- Significantly hardened minimal-format support (RHE, R-only, no line score, `x` values).
- Introduced defensive-outs derivation and centralized fieldnames constants for maintainability.
- Full-season testing (60+ games per team) completed successfully with no runtime errors.

---

*This document supersedes the original Functional Specification from Fall 2025.*