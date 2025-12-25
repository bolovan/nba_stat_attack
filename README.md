# 🏀 NBA Stat Attack

A turn-based RPG battle game that transforms real NBA player statistics into strategic combat mechanics. Use actual basketball box scores as "Gametapes" to power your fighters!

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.28+-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 🎮 Game Overview

NBA Stat Attack converts real NBA game data into an engaging combat system:

- **Players** are fighters with base stats derived from their season averages. All players selected randomly. Starting from 2016-2017 season to 2024-2025 season.
- **Gametapes** are equipment that modify stats based on specific real-life box score stats from games.
- **Labels** are special bonuses earned from strong performances (Triple Double, Microwave, etc.)

## ⚔️ Battle System

### 1v1 Duels
Turn-based combat where your action deck is generated from real box scores:

| Box Score Stat | Battle Action |
|---------------|---------------|
| Field Goals Made | Attack |
| 3-Pointers Made | Strong Attack |
| Free Throws Made | Weak Attack |
| Missed Shots | Miss (wasted turn) |
| Defensive Rebounds | Defense Buff |
| Offensive Rebounds | Self-Heal |
| Assists | Attack Buff |
| Steals | Opponent Attack Debuff |
| Blocks | Opponent Defense Debuff |
| Turnovers | Skip Turn |
| Fouls | Self-Damage |

### 5v5 Coach Mode
Simulated team battles where you select offensive and defensive strategies:

**Offensive Strategies:**
- 🔥 Feed the Hot Hand - Prioritize your strongest attacker
- 🏀 Ball Movement - String assists before attacking
- 💪 Crash the Glass - Focus on offensive rebounds to heal
- ⚡ 7 Seconds or Less - Relentless attacking

**Defensive Strategies:**
- 🛡️ Lockdown Paint - Prioritize blocks
- 🏃 Full Court Press - Prioritize steals
- 📦 Box Out - Prioritize defensive rebounds
- 🔄 Switch Everything - Balanced defense

## 🏷️ Special Labels

Gametapes can earn powerful labels based on performance:

| Label | Requirement | Bonus |
|-------|-------------|-------|
| Triple Double | 10+ in 3 categories | +25% Defense |
| Microwave | 15+ pts in ≤24 min | Double damage on first hit |
| Stopper | High deflections/charges | Adds 2 misses to opponent |
| Floor General | 6+ AST, 3+ AST/TO ratio | Assists grant 2x buff stacks |
| Rim Protector | 2+ BLK, 8+ DREB | Blocks debuff 2x |
| Bruiser | 4+ screen assists | +30 Max HP |
| 3 and D | >2 fg3m, assisted, low usage | Removes 2 misses from movelist |
| Glue Guy | +10 +/-, 3+ AST, ≤15 PTS | Adds 4 bonus free throws |

## 💰 Economy

- **Tokens**: Earned from battles (more for winning)
- **Gametape Cost**: 3 tokens
- **Player Card Cost**: 5 tokens
- **Hall of Fame**: 16 wins retires a gametape as a legend (+8 bonus tokens)
- **G-League**: 4 losses removes a gametape from your inventory

## 🚀 Running Locally

### Prerequisites
- Python 3.9+
- SQLite database file (`nba_stats.db`)

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/nba-stat-attack.git
cd nba-stat-attack

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

### Database
The game requires an `nba_stats.db` SQLite file containing:
- `players` table (id, full_name)
- `game_logs` table (player stats per game)
- `box_scores` table (advanced stats JSON)

## 📁 Project Structure

```
nba-stat-attack/
├── app.py              # Streamlit UI and main game loop
├── game_manager.py     # Inventory, saves, and game progression
├── battle_engine.py    # Combat mechanics and battle resolution
├── game_config.py      # Game formulas and constants
├── nba_data.py         # Database queries and data management
├── nba_stats.db        # SQLite database (not included)
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## 🎯 How to Play

1. **Start**: You begin with one random player and gametape
2. **Battle**: Win 1v1 duels to earn tokens
3. **Shop**: Buy new players and gametapes with tokens
4. **Build**: Collect 5 players with gametapes to unlock 5v5 mode
5. **Unlock 5v5**: Win 41 total games to access Coach Mode
6. **Hall of Fame**: Get 16 wins with a gametape to immortalize it

## 💾 Save System

- Progress auto-saves after each battle
- Download/upload save files via Settings menu
- Save files are portable JSON format

## 🔧 Configuration

Key settings in `game_config.py`:
- `GAMES_TO_UNLOCK_5V5 = 41` - Wins needed for Coach Mode
- `GAMETAPE_MAX_WINS = 16` - Wins for Hall of Fame
- `GAMETAPE_MAX_LOSSES = 4` - Losses before gametape is cut

## 📊 Data Sources

This game uses historical NBA box score data from seasons 2016-17 through 2024-25.

## 🤝 Contributing

Contributions welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

## 📜 License

MIT License - feel free to use and modify!

## 🙏 Acknowledgments

- NBA for the incredible game and statistics
- Streamlit for the amazing web framework
- All the basketball fans who inspired this project

---

**Play Ball! 🏀**
