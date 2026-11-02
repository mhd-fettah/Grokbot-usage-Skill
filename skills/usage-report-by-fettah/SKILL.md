---
name: Usage Report by Fettah
description: >-
  Use when the user asks for a usage report, how their Grok Bot usage is going,
  a usage breakdown, whether they will run short or have usage to spare before
  the weekly reset, or to switch the report card between light and dark mode.
  Version 1.2.
---
# Usage Report by Fettah (v1.2)

Draws a designed PNG report card of the user's weekly Grok Bot usage: percent used, time until reset, a breakdown by bot and routine, and an hour-based pace verdict (Spare, Close, or Short). The card is drawn by a local Python script, never by hand, never by AI image generation, and never replaced by a text or table report.

Files live in `/home/box/agent-data/scripts/usage_card/`: `usage_card.py`, `fonts/`, `preferences.json`.

## Setup (check before every report)
Run `python3 /home/box/agent-data/scripts/usage_card/usage_card.py --version`. If it fails or doesn't print exactly `v22`, run this whole block in one Shell call, copied verbatim. It installs Pillow if missing, downloads the open-source Inter font, downloads the script from the public repo, and prints `v22`. It never touches `preferences.json`. If the font download fails, the script still renders with a default font.

```bash
D=/home/box/agent-data/scripts/usage_card
mkdir -p "$D/fonts"
python3 -c "import PIL" 2>/dev/null || pip install --quiet Pillow || pip install --quiet --break-system-packages Pillow
[ -s "$D/fonts/Inter-VariableFont_opsz,wght.ttf" ] || curl -fsSL -o "$D/fonts/Inter-VariableFont_opsz,wght.ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"
curl -fsSL https://raw.githubusercontent.com/mhd-fettah/Grokbot-usage-Skill/MASTER/usage_card.py -o "$D/usage_card.py"
python3 "$D/usage_card.py" --version
```

## Preferences
`/home/box/agent-data/scripts/usage_card/preferences.json`, e.g. `{"theme": "light", "layout": "lines"}`. `theme` is "light" or "dark".
- If the file doesn't exist, ask with a widget "Should your usage report card be light or dark?" (Light / Dark), save the answer with layout "lines", then continue.
- When the user asks to switch light or dark, update the file and confirm in one line.

## Steps
1. Load the `usage-review` skill and follow its reporting rules (real numbers only, plain names).
2. Run the setup check above.
3. Read the preferences file.
4. Call CheckSubscriptionUsage once with `breakdown: ["bot", "routine"]`. Note the percent of the weekly limit used, the exact reset time, and the bot and routine shares. If usage just reset and shares are empty, also call it with `period: "last_7_days"` for the breakdown only.
5. Compute `hours_left` until the reset (one decimal) from the current time in the user's time zone.
6. Write `/workspace/usage_input.json` with:
   - `used_pct` (float), `hours_left` (float)
   - `reset_label`: reset time in the user's zone with a short zone label, e.g. "Sat, Nov 7 · 4:50 AM (Dubai time)"
   - `reset_iso`: exact reset time as ISO 8601 with the user's UTC offset, e.g. "2026-11-07T04:50:00+04:00"
   - `generated_label`: now, same style
   - `theme`, `layout`: from preferences
   - `breakdown`: list of `{"name", "pct", "children": [{"name", "pct"}]}` from the shares (percent of Grok Bot usage), routine names shortened, "Not from a routine" shown as "Regular chat". Bot names without emoji.
   - `ranout_iso` (only if `used_pct` >= 100 and the daily breakdown shows when 100% was hit): that moment as ISO 8601 with the user's offset. Otherwise omit it; the script estimates.
7. Render: `python3 /home/box/agent-data/scripts/usage_card/usage_card.py /workspace/usage_input.json --out /workspace/usage_card_<timestamp>.png` (fresh filename each time). It prints a JSON summary (verdict, detail, rates, projection).
8. Send the PNG as an attachment, then one or two lines with the verdict and its figure, noting it's an estimate from the average pace so far.
9. If Short, offer up to three ways to use less from the `usage-review` skill and wait for a yes. If Spare, mention there's room for heavier work before the reset.

If the script still fails after running setup, say so plainly and show the error; don't draw a substitute card.

## Pace math (what the script does)
- E = 168 - hours_left. Too early if E < 6 or used is 0.
- R = used / E; hours to 100% = (100 - used) / R; projected P = used + R x hours_left; even pace = E / 168 x 100.
- Short (red) if hours to 100% < hours_left - 2; Spare (green) if P < 90; otherwise Close (orange).
- Used >= 100: Ran out (red), "Limit reached"; run-out time from `ranout_iso`, else estimated as E x 100 / used.
- Card: usage bar (0-100%) stacked on the week bar on one shared axis; the Now line is also even pace.
