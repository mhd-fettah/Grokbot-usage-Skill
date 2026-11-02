# Grok Bot Usage Report

This repo stores the whole **Grok Bot Usage Report** bot, made by Fettah: the card script, the bot's skills and its setup files. The bot draws your weekly Grok Bot usage report card, with a pace forecast and a per-bot breakdown, in light or dark mode.

## Layout
- `usage_card.py`: the card script (v22).
- `skills/usage-report-by-fettah/SKILL.md`: the report skill. Its Setup downloads the script from this repo.
- `skills/usage-report-by-fettah-setup/SKILL.md`: the first-chat skill (welcome, Light or Dark, first card).
- `bot/profile.json`: the bot's name and description.
- `bot/memories.md`: the bot's memories. On the first chat they install the skills from this repo.

The bot sets itself up from these files. You don't need to do anything by hand.

## One-line install (script only)
```bash
mkdir -p /home/box/agent-data/scripts/usage_card && curl -fsSL https://raw.githubusercontent.com/mhd-fettah/Grokbot-usage-Skill/MASTER/usage_card.py -o /home/box/agent-data/scripts/usage_card/usage_card.py && python3 /home/box/agent-data/scripts/usage_card/usage_card.py --version
```
It needs Pillow (`pip install pillow`) and prints `v22`.

Made by Fettah · v1.2
