# Baseball Box Score Parser (extract_boxscores.py)

A Python script to parse historical minor league baseball box scores from text files (newspapers and other sources) into structured CSV files for analysis. Output follows a Retrosheet-inspired format.

## Supported Input Formats

The parser handles a wide range of 1907-era (and similar) newspaper box score styles:

- **Full / Maximum box scores** — Complete player batting, pitching, and fielding lines, line scores (inning-by-inning), TOTALS lines, batteries, umpires, time, attendance, etc.
- **Minimal RHE box scores** — Only Runs, Hits, and Errors shown for players (often marked with `x` for missing values). Line scores are usually present.
- **R-only or partial stats** — Very minimal formats that may show only runs or a subset of columns.
- **No line score** — Games where inning-by-inning data is missing.
- **Postponed games** — Identified by `status: postponed` (optionally with `status-reason`).
- **Forfeited games** — Identified by `status: forfeit` (see conventions below).

The script is robust to missing values (`x` or blank), inconsistent headers, and varying name formats. It standardizes player names via `playerID` where possible and logs discrepancies between player sums and reported TOTALS.

## Key Conventions

### Postponed Games
Use the following in the box score text:

```
status: postponed
status-reason: rain
```

**Output behavior:**
- Only `gameinfo.csv` is written (with `status` and `status-reason` populated).
- No rows are written to `teamstats.csv`, `batting.csv`, `pitching.csv`, or `fielding.csv`.

### Forfeited Games
Use the following in the box score text:

```
status: forfeit
forfeit-to: home     (or forfeit-to: away)
```

- `forfeit-to: home` → Home team is the winner
- `forfeit-to: away` → Away team is the winner

**Two types of forfeits are supported:**

1. **Type 1 – Pre-game / Before the game became official**  
   No player lines or real statistics.  
   **Output:** Minimal `gameinfo.csv` (with `forfeit = 'Y'`, `wteam`, `lteam`) + minimal `teamstats.csv` rows containing only `win`/`loss` flags.

2. **Type 2 – After the game became official**  
   A normal (or partial) box score exists.  
   **Output:** Full normal processing + `forfeit = 'Y'` added to the `gameinfo.csv` row.

Umpires listed with `U:` are captured in `gameinfo.csv` when available.

## Minimal vs. Full Box Scores

| Aspect                  | Full / Maximum Box Score                  | Minimal Box Score                          |
|-------------------------|-------------------------------------------|--------------------------------------------|
| Player lines            | Complete stats                            | Often `x` or missing values                |
| Line score              | Usually present                           | May be present or absent                   |
| TOTALS line             | Expected and validated                    | May be partial or use line-score fallback  |
| Defensive outs (d_ifouts, p_ipouts) | From explicit stats or TOTALS     | Last-resort derivation from line score when possible |
| `vruns` / `hruns`       | From line score or totals                 | From line score (with fallback)            |
| `win` / `loss`          | From explicit stats or wteam/lteam        | From `forfeit-to` or normal logic          |
| Output files            | All CSVs populated                        | Only relevant CSVs (e.g., gameinfo + minimal teamstats for Type 1 forfeits) |

The parser uses safe handling for missing data and last-resort calculations (e.g., defensive outs from line score innings × 3) only when explicit data is absent.

## Output Files

- `gameinfo.csv` — Game-level metadata, scores, status, forfeit flags, umpires, etc.
- `teamstats.csv` — Team-level batting, pitching, fielding, and win/loss data.
- `batting.csv` — Individual player batting lines.
- `pitching.csv` — Individual player pitching lines.
- `fielding.csv` — Individual player fielding lines.
- `discrepancies.csv` — Logged differences between player sums and reported TOTALS.
- `notes.csv` — Any notes or special remarks from the source.

## Configuration

- `config.ini` — Defines the input `boxscore_folder` and other settings.
- `team_abbreviations.csv` — Maps full team names to standard abbreviations (e.g., `Greenwood → GRE`).

## Usage

```bash
python extract_boxscores.py --file your_boxscore.txt --debug
```

Or process all files in the configured folder by running without the `--file` argument.

## Notes

- The script is designed for historical minor league data and is intentionally tolerant of the inconsistencies common in early 20th-century newspaper box scores.
- Always review `discrepancies.csv` after a run.
- For best results, provide complete TOTALS lines when possible.

---

*Maintained as part of the "Parsing box scores" project.*