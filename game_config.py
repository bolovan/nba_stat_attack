"""
NBA Stat Attack Configuration
Contains all game formulas, constants, and settings
"""

# Base stats for all players
BASE_HP = 100
BASE_ATTACK = 10
BASE_DEFENSE = 10

# Stat conversion rates (Season Averages → Base Stats)
PPG_TO_ATTACK = 0.3
APG_TO_ATTACK = 0.2
TOV_TO_ATTACK = -0.15
RPG_TO_DEFENSE = 0.25
SPG_TO_DEFENSE = 1.5
BPG_TO_DEFENSE = 1.5
MPG_TO_HP = 2  # Each minute above/below 24 MPG adjusts HP by this amount
AVERAGE_MPG = 24  # League average minutes

# Move type damage multipliers
WEAK_ATTACK_MULTIPLIER = 0.5
REGULAR_ATTACK_MULTIPLIER = 1.0
STRONG_ATTACK_MULTIPLIER = 1.5

# Buff/Debuff percentages
BUFF_MULTIPLIER = 1.3
DEBUFF_MULTIPLIER = 0.7

# Health modifiers
OFFENSIVE_REBOUND_HEAL_BASE = 0.15  # 15% base heal
FOUL_DAMAGE = 0.167  # 16.7% HP loss
TECHNICAL_DAMAGE = 0.5  # 50% HP loss

# Token economy
TOKENS_WIN_1V1 = 2
TOKENS_LOSE_1V1 = 1
TOKENS_WIN_5V5 = 5
TOKENS_LOSE_5V5 = 1
GAMETAPE_COST = 3
PLAYER_CARD_COST = 5
GAMETAPE_SELL_VALUE = 1
PLAYER_CARD_SELL_VALUE = 3

# Gametape retirement conditions
GAMETAPE_MAX_WINS = 16
GAMETAPE_MAX_LOSSES = 4
GAMETAPE_RETIREMENT_BONUS = 8

# Game requirements
MIN_MINUTES_PLAYED = 8
MIN_MOVES_REQUIRED = 10
MIN_AVERAGE_MPG = 8  # Players averaging less than this are excluded
MAX_ROSTER_SIZE = 5
GAMES_TO_UNLOCK_5V5 = 41

# API Rate limiting settings
API_DELAY_SECONDS = 0.6  # Delay between API calls to avoid rate limits
MAX_RETRIES = 3

def calculate_base_stats(player_stats):
    """
    Calculate base stats from season averages
    """
    ppg = player_stats.get('PTS', 0)
    apg = player_stats.get('AST', 0)
    tov = player_stats.get('TOV', 0)
    rpg = player_stats.get('REB', 0)
    spg = player_stats.get('STL', 0)
    bpg = player_stats.get('BLK', 0)
    mpg = player_stats.get('MIN', 0)
    
    attack = BASE_ATTACK + (ppg * PPG_TO_ATTACK) + (apg * APG_TO_ATTACK) + (tov * TOV_TO_ATTACK)
    defense = BASE_DEFENSE + (rpg * RPG_TO_DEFENSE) + (spg * SPG_TO_DEFENSE) + (bpg * BPG_TO_DEFENSE)
    hp = BASE_HP + ((mpg - AVERAGE_MPG) * MPG_TO_HP)
    
    return {
        'hp': max(50, hp),  # Minimum 50 HP
        'attack': max(5, attack),  # Minimum 5 attack
        'defense': max(5, defense)  # Minimum 5 defense
    }

def calculate_deviation_multiplier(game_value, season_average):
    """
    Calculate buff/debuff multiplier based on deviation from season average
    """
    if season_average == 0:
        season_average = 0.1  # Avoid division by zero
    
    multiplier = 0.5 + (game_value / season_average) * 0.5
    return max(0.5, min(2.0, multiplier))  # Cap between 0.5x and 2.0x

def calculate_damage(attack, defense, attack_type='regular'):
    """
    Calculate damage dealt based on attack vs defense
    """
    multipliers = {
        'weak': WEAK_ATTACK_MULTIPLIER,
        'regular': REGULAR_ATTACK_MULTIPLIER,
        'strong': STRONG_ATTACK_MULTIPLIER
    }
    
    type_mult = multipliers.get(attack_type, REGULAR_ATTACK_MULTIPLIER)
    
    # Significantly reduced damage formula
    base_damage = (attack ** 2 / (attack + defense)) * 1.8
    final_damage = base_damage * type_mult
    
    return max(1, int(final_damage))  # Minimum 1 damage

def apply_stack_decay(stack_count):
    """
    Apply diminishing returns to stacked buffs/debuffs
    """
    if stack_count == 0:
        return 1.0
    
    is_negative = stack_count < 0
    count = abs(stack_count)
    
    # Calculate magnitude of the effect based on count
    # Formula creates a curve that grows but slows down (diminishing returns)
    magnitude = count * 0.3 * (0.9 ** (count - 1))
    
    if is_negative:
        # For debuffs: Reduce the multiplier below 1.0
        # Example: Magnitude 0.1 -> 1 / 1.1 = 0.909 (approx 9% reduction)
        return 1.0 / (1.0 + magnitude)
    else:
        # For buffs: Increase the multiplier above 1.0
        # Example: Magnitude 0.1 -> 1.1 (10% boost)
        return 1.0 + magnitude


def calculate_offensive_rebound_heal(rpg):
    """
    Calculate heal percentage based on rebounding ability
    """
    heal_percent = OFFENSIVE_REBOUND_HEAL_BASE + (rpg / 10 * 0.01)
    return min(0.25, heal_percent)  # Cap at 25% heal

def calculate_power_rating(hp, attack, defense, moves):
    """
    Calculate a simple power rating for quick comparison
    """
    # Count move types
    strong_attacks = sum(1 for m in moves if m['type'] == 'strong_attack')
    regular_attacks = sum(1 for m in moves if m['type'] == 'attack')
    weak_attacks = sum(1 for m in moves if m['type'] == 'weak_attack')
    buffs = sum(1 for m in moves if m['type'] in ['assist', 'defensive_rebound'])
    misses = sum(1 for m in moves if m['type'] == 'miss')
    turnovers = sum(1 for m in moves if m['type'] == 'turnover')
    
    move_quality = (strong_attacks * 3) + (regular_attacks * 2) + (weak_attacks * 1) + \
                   (buffs * 2) - (misses * 0.5) - (turnovers * 3)
    
    power_rating = (hp * 0.3) + (attack * 2) + (defense * 2) + (move_quality * 0.5)
    
    return int(power_rating)

def get_valid_input(prompt, max_value, min_value=1):
    """
    Safely get user input between min_value and max_value
    """
    while True:
        try:
            choice = input(prompt)
            # Check for empty input
            if not choice.strip():
                print("Please enter a number.")
                continue
                
            val = int(choice)
            if min_value <= val <= max_value:
                return val
            else:
                print(f"Please enter a number between {min_value} and {max_value}.")
        except ValueError:
            print("Invalid input! Please enter a number.")