# IPL Fantasy — Google Sheet formula set

The auction page only writes two columns in **`IPL_FANTASY_PLAYER_DASH`**:
**F = Sold To** (exact team name, or `UNSOLD`, or blank) and **G = Final Price (Cr)**.
Everything on the dashboard is computed by the formulas below — paste these into
**`IPL_FANTASY_LIV_DASH`**, one row per team.

**Budget: ₹40 Cr per team** (the `40-` at the start of the Budget Left formula). If you
ever change the budget, change it there and in `ipl-auction.html` → `CONFIG.BUDGET` — the
two must always match.

Assumes:
- `IPL_FANTASY_PLAYER_DASH` has 120 players in **rows 2–121**
  (A=Player ID, B=Name, C=Role, D=Skill, E=Base, F=Sold To, G=Final Price).
- `IPL_FANTASY_LIV_DASH` has the 8 teams in **rows 2–9**
  (A=Team Name, B=Budget Left, C=Players Bought, D=Batsmen, E=Bowlers,
  F=All-Rounders, G=Wicket-Keepers, H=Total Skill Points, I=Final Team Score, J=Max Bid).

## Paste into row 2, then fill down to row 9

| Col | Field | Formula (row 2) |
|-----|-------|-----------------|
| **B** | Budget Left | `=40-SUMIF(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2,IPL_FANTASY_PLAYER_DASH!$G$2:$G$121)` |
| **C** | Players Bought | `=COUNTIF(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2)` |
| **D** | Batsmen | `=COUNTIFS(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2,IPL_FANTASY_PLAYER_DASH!$C$2:$C$121,"BAT")` |
| **E** | Bowlers | `=COUNTIFS(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2,IPL_FANTASY_PLAYER_DASH!$C$2:$C$121,"BOWL")` |
| **F** | All-Rounders | `=COUNTIFS(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2,IPL_FANTASY_PLAYER_DASH!$C$2:$C$121,"AR")` |
| **G** | Wicket-Keepers | `=COUNTIFS(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2,IPL_FANTASY_PLAYER_DASH!$C$2:$C$121,"WK")` |
| **H** | Total Skill Points | `=SUMIF(IPL_FANTASY_PLAYER_DASH!$F$2:$F$121,$A2,IPL_FANTASY_PLAYER_DASH!$D$2:$D$121)` |
| **I** | Final Team Score | `=H2*IF(AND($C2=11,$D2>=4,$E2>=4,$F2>=1,$G2>=1),1,0.8)+MIN(3,0.2*$B2)` |
| **J** | Max Bid | `=IF(11-$C2<=0,0,$B2-((11-$C2-1)*0.2))` |

## How these map to the rulebook

- **Final Team Score** `= (Total Skill × Balance Modifier) + Budget Bonus`
  - Balance Modifier = **1.0** only if the squad is complete (11 players **and** ≥4 BAT, ≥4 BOWL, ≥1 AR, ≥1 WK), else **0.8** (the `IF(AND(...),1,0.8)`).
  - Budget Bonus = **+0.20 per ₹1 Cr left**, capped at **+3.00** (the `MIN(3,0.2*B)`).
- **Max Bid** `= Budget Left − ((slots still open − 1) × ₹0.20 Cr)`, where open slots = `11 − Players Bought`. When the squad is full it shows **0**.

> ⚠️ **One thing to check:** your current sheet shows Max Bid = **₹97.80** for a fresh team,
> which comes from `Budget − (openSlots × 0.20)`. The rulebook formula subtracts
> `(openSlots − 1)`, giving **₹98.00** at the start. The formula above follows the
> **rulebook (₹98.00)**. Keep whichever you prefer — just be consistent.

## Notes
- Matching is on the **exact team name** text in column A, so the auction tool writes
  team names exactly as they appear here. `UNSOLD` and blank never match a team, so
  unsold/not-yet-auctioned players are correctly excluded from every total.
- Final Price (column G) must be **numbers** for `SUMIF` to add them. The auction tool
  always writes numbers, so this is automatic.
- **Optional player photos:** add a header **`Photo URL`** in column **H** of
  `IPL_FANTASY_PLAYER_DASH` and paste an image link for any player. The auction card
  shows that image; if the cell is blank (or the link breaks) it falls back to a
  coloured initials avatar. No photos are required.
