# Grok Bot Usage Report

This repo holds the card script for the **Grok Bot Usage Report** bot template, made by Fettah. The script draws your weekly Grok Bot usage report card. It shows a pace forecast and a per-bot breakdown, in light or dark mode.

The bot downloads `usage_card.py` from this repo when it first sets up. You don't need to do anything by hand.

## Manual install
```bash
mkdir -p /home/box/agent-data/scripts/usage_card
curl -fsSL https://raw.githubusercontent.com/mhd-fettah/Grokbot-usage-Skill/MASTER/usage_card.py -o /home/box/agent-data/scripts/usage_card/usage_card.py
pip install --quiet pillow
python3 /home/box/agent-data/scripts/usage_card/usage_card.py --version   # prints v22
```

Made by Fettah · v1.2
