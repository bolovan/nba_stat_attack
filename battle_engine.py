"""
Battle Engine
Handles all combat mechanics, turn management, and battle resolution
"""

import random
import math
import copy
import game_config as config

class BattleUnit:
    """Represents a player in battle with their stats and action deck"""
    
    def __init__(self, player_card, gametape, season_stats):
        self.name = player_card['full_name']
        self.player_id = player_card['id']
        
        # Calculate base stats
        base_stats = config.calculate_base_stats(season_stats)
        
        # Apply gametape deviations
        self.calculate_battle_stats(base_stats, gametape, season_stats)
        
        # Extract raw move list and labels
        if isinstance(gametape['moves'], dict):
            raw_moves = gametape['moves'].get('moves', [])
            self.labels = gametape['moves'].get('labels', [])
            self.plus_minus = gametape['moves'].get('plus_minus', 0)
        else:
            raw_moves = gametape['moves'] if isinstance(gametape['moves'], list) else []
            self.labels = []
            self.plus_minus = 0
            
        # --- DECK BUILDING LOGIC ---
        self.timeouts_remaining = 2
        self.action_deck = {
            'attack': 0,
            'defensive_rebound': 0,
            'offensive_rebound': 0,
            'assist': 0,
            'steal': 0,
            'block': 0
        }
        
        # Track probability pools
        self.attack_pool = [] # ['strong', 'weak', 'regular', 'miss']
        self.total_actions_in_tape = len(raw_moves) if raw_moves else 1
        
        tov_count = 0
        foul_count = 0
        
        for move in raw_moves:
            m_type = move['type']
            
            # Categorize Moves
            if m_type in ['attack', 'strong_attack', 'weak_attack', 'miss']:
                self.action_deck['attack'] += 1
                if m_type == 'attack': self.attack_pool.append('regular')
                elif m_type == 'strong_attack': self.attack_pool.append('strong')
                elif m_type == 'weak_attack': self.attack_pool.append('weak')
                elif m_type == 'miss': self.attack_pool.append('miss')
                
            elif m_type == 'defensive_rebound':
                self.action_deck['defensive_rebound'] += 1
            elif m_type == 'offensive_rebound':
                self.action_deck['offensive_rebound'] += 1
            elif m_type == 'assist':
                self.action_deck['assist'] += 1
            elif m_type == 'steal':
                self.action_deck['steal'] += 1
            elif m_type == 'block':
                self.action_deck['block'] += 1
            elif m_type == 'turnover':
                tov_count += 1
            elif m_type in ['foul', 'technical', 'ejection']:
                foul_count += 1
                
        self.tov_chance = tov_count / self.total_actions_in_tape
        self.foul_chance = foul_count / self.total_actions_in_tape
        
        self.max_deck = self.action_deck.copy()
        
        # Battle state
        self.current_hp = self.max_hp
        self.attack_buff_stacks = 0
        self.defense_buff_stacks = 0
        self.skip_next_turn = False
        self.microwave_used = False
        
        # Apply label stat bonuses BEFORE calculating power rating
        self.apply_label_stat_bonuses()
        
        # Update current_hp after potential Bruiser bonus
        self.current_hp = self.max_hp

        # Power Rating
        self.power_rating = config.calculate_power_rating(
            self.max_hp, self.attack, self.defense, raw_moves
        )
    
    def apply_label_stat_bonuses(self):
        if 'Triple Double' in self.labels: self.defense *= 1.25
        if 'Bruiser' in self.labels: self.max_hp += 30
    
    def calculate_battle_stats(self, base_stats, gametape, season_stats):
        game_stats = gametape['game_stats']
        
        # Calculate multipliers
        pts_mult = config.calculate_deviation_multiplier(game_stats['pts'], season_stats['PTS'])
        ast_mult = config.calculate_deviation_multiplier(game_stats['ast'], season_stats['AST'])
        tov_mult = config.calculate_deviation_multiplier(game_stats['tov'], season_stats['TOV'] if season_stats['TOV'] > 0 else 0.1)
        reb_mult = config.calculate_deviation_multiplier(game_stats['reb'], season_stats['REB'])
        stl_mult = config.calculate_deviation_multiplier(game_stats['stl'], season_stats['STL'] if season_stats['STL'] > 0 else 0.1)
        blk_mult = config.calculate_deviation_multiplier(game_stats['blk'], season_stats['BLK'] if season_stats['BLK'] > 0 else 0.1)
        min_mult = config.calculate_deviation_multiplier(game_stats['min'], season_stats['MIN'])
        
        # Attack
        attack_from_pts = season_stats['PTS'] * config.PPG_TO_ATTACK * pts_mult
        attack_from_ast = season_stats['AST'] * config.APG_TO_ATTACK * ast_mult
        attack_from_tov = season_stats['TOV'] * config.TOV_TO_ATTACK * tov_mult
        self.attack = max(5, config.BASE_ATTACK + attack_from_pts + attack_from_ast + attack_from_tov)
        
        # Defense
        defense_from_reb = season_stats['REB'] * config.RPG_TO_DEFENSE * reb_mult
        defense_from_stl = season_stats['STL'] * config.SPG_TO_DEFENSE * stl_mult
        defense_from_blk = season_stats['BLK'] * config.BPG_TO_DEFENSE * blk_mult
        self.defense = max(5, config.BASE_DEFENSE + defense_from_reb + defense_from_stl + defense_from_blk)
        
        # HP
        hp_adjustment = (season_stats['MIN'] - config.AVERAGE_MPG) * config.MPG_TO_HP * min_mult
        self.max_hp = max(50, config.BASE_HP + hp_adjustment)
        
        self.rpg = season_stats['REB']
    
    def is_alive(self):
        # Using a small threshold for floating point safety, but display uses ceil
        return self.current_hp > 0.1
    
    def deck_is_empty(self):
        return all(count == 0 for count in self.action_deck.values())

    def refill_deck(self, percentage):
        for action, max_val in self.max_deck.items():
            if max_val > 0:
                if percentage == 0.25: # Empty Reset
                    self.action_deck[action] = math.ceil(max_val * percentage)
                else: # Timeout (Refill)
                    used = max_val - self.action_deck[action]
                    restore = math.ceil(used * 0.5)
                    self.action_deck[action] = min(max_val, self.action_deck[action] + restore)


class Battle:
    """Manages an interactive 1v1 turn-based battle"""
    
    def __init__(self, unit1, unit2):
        self.player = unit1
        self.opponent = unit2
        self.turn_count = 0
        self.battle_log = []
        
        # Apply Stopper label effects (adds misses to opponent)
        self.apply_stopper_effect(unit1, unit2)
        self.apply_stopper_effect(unit2, unit1)

        if unit1.plus_minus >= unit2.plus_minus:
            self.current_turn = 'player'
            self.first_reason = f"higher +/- ({unit1.plus_minus} vs {unit2.plus_minus})"
        else:
            self.current_turn = 'opponent'
            self.first_reason = f"higher +/- ({unit2.plus_minus} vs {unit1.plus_minus})"

    def apply_stopper_effect(self, stopper_unit, target_unit):
    # If stopper_unit has Stopper label, add 2 misses to target's attack pool #
        if 'Stopper' in stopper_unit.labels:
            target_unit.attack_pool.append('miss')
            target_unit.attack_pool.append('miss')

    def log(self, message):
        print(message)
        self.battle_log.append(message)

    def execute_battle(self):
        self.log(f"\n{'='*60}")
        self.log(f"BATTLE START!")
        self.log(f"{self.player.name} vs {self.opponent.name}")
        self.log(f"{'You' if self.current_turn == 'player' else self.opponent.name} go first ({self.first_reason})")
        self.log(f"{'='*60}\n")
        
        self.display_status()
        
        while self.player.is_alive() and self.opponent.is_alive():
            self.turn_count += 1
            self.log(f"\n--- TURN {self.turn_count} ---")
            
            if self.player.deck_is_empty():
                self.log(f"🔄 {self.player.name}'s actions exhausted! Loop Reset")
                self.player.refill_deck(0.25)
            if self.opponent.deck_is_empty():
                self.log(f"🔄 {self.opponent.name}'s actions exhausted! Loop Reset")
                self.opponent.refill_deck(0.50)

            if self.current_turn == 'player':
                if self.player.skip_next_turn:
                    self.log(f"🚫 You lose this turn due to turnover!")
                    self.player.skip_next_turn = False
                else:
                    self.player_turn_logic()
                self.current_turn = 'opponent'
            else:
                if self.opponent.skip_next_turn:
                    self.log(f"🚫 {self.opponent.name} loses turn due to turnover!")
                    self.opponent.skip_next_turn = False
                else:
                    self.opponent_turn_logic()
                self.current_turn = 'player'
                
            if not self.player.is_alive() or not self.opponent.is_alive():
                break
                
        winner = self.player if self.player.is_alive() else self.opponent
        loser = self.opponent if winner == self.player else self.player
        
        self.display_status()
        self.log(f"\n{'='*60}")
        self.log(f"BATTLE ENDED! Winner: {winner.name}")
        self.log(f"{'='*60}\n")
        
        return {'winner': winner, 'loser': loser, 'turns': self.turn_count}

    def display_status(self):
        p_hp = math.ceil(self.player.current_hp)
        o_hp = math.ceil(self.opponent.current_hp)
        p_max = math.ceil(self.player.max_hp)
        o_max = math.ceil(self.opponent.max_hp)
        print(f"\n[YOU] {self.player.name}: {p_hp}/{p_max} HP")
        print(f"[OPP] {self.opponent.name}: {o_hp}/{o_max} HP")

    def player_turn_logic(self):
        self.display_status()
        print("\nCHOOSE YOUR ACTION:")
        
        options = [
            ('attack', 'Attack'),
            ('defensive_rebound', 'Def Rebound'),
            ('offensive_rebound', 'Off Rebound'),
            ('assist', 'Assist'),
            ('steal', 'Steal'),
            ('block', 'Block')
        ]
        
        valid_choices = []
        for idx, (key, label) in enumerate(options):
            count = self.player.action_deck[key]
            print(f"{idx+1}. {label} ({count} remaining)")
            if count > 0:
                valid_choices.append(idx+1)
                
        to_label = f"Timeout ({self.player.timeouts_remaining} left)"
        print(f"7. {to_label}")
        if self.player.timeouts_remaining > 0:
            valid_choices.append(7)
            
        while True:
            try:
                choice = int(input("Select Action (1-7): "))
                if choice in valid_choices:
                    break
                print("Invalid choice or no actions left.")
            except ValueError:
                print("Please enter a number.")
        
        if choice == 7:
            self.execute_timeout(self.player)
        else:
            action_key = options[choice-1][0]
            self.player.action_deck[action_key] -= 1
            self.resolve_action(self.player, self.opponent, action_key)

    def opponent_turn_logic(self):
        available = [k for k, v in self.opponent.action_deck.items() if v > 0]
        if not available: return
        action_key = random.choice(available)
        self.opponent.action_deck[action_key] -= 1
        self.resolve_action(self.opponent, self.player, action_key)

    def execute_timeout(self, unit):
        unit.timeouts_remaining -= 1
        unit.refill_deck(0.5)
        self.log(f"🛑 {unit.name} calls Timeout! Actions partially restored.")

    def resolve_action(self, attacker, defender, action_type):
        # Mistakes
        if action_type in ['attack', 'assist']:
            if random.random() < attacker.tov_chance:
                attacker.skip_next_turn = True
                self.log(f"⚠️ {attacker.name} commits a TURNOVER! Next turn skipped.")
                return

        if action_type in ['attack', 'steal', 'block']:
            if random.random() < attacker.foul_chance:
                dmg = attacker.max_hp * config.FOUL_DAMAGE
                attacker.current_hp = max(0, attacker.current_hp - dmg)
                self.log(f"⚠️ {attacker.name} commits a FOUL! Takes {dmg:.1f} recoil damage.")
        
        # Execute
        if action_type == 'attack':
            self.resolve_attack(attacker, defender)
        elif action_type == 'defensive_rebound':
            attacker.defense_buff_stacks += 1
            buff = config.apply_stack_decay(attacker.defense_buff_stacks)
            self.log(f"🛡️ {attacker.name} grabs Defensive Rebound! Defense buffed to {buff:.2f}x")
        elif action_type == 'offensive_rebound':
            heal = attacker.max_hp * config.calculate_offensive_rebound_heal(attacker.rpg)
            attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal)
            self.log(f"🩹 {attacker.name} grabs Offensive Rebound! Heals {heal:.1f} HP")
        elif action_type == 'assist':
            stacks = 1
            # --- Floor General Bonus ---
            if 'Floor General' in attacker.labels:
                stacks = 2
                self.log(f"🧠 {attacker.name}'s Floor General Bonus! +1 Extra Stack")
            attacker.attack_buff_stacks += stacks
            buff = config.apply_stack_decay(attacker.attack_buff_stacks)
            self.log(f"🏀 {attacker.name} dishes an Assist! Next attack buffed to {buff:.2f}x")
        elif action_type == 'steal':
            defender.attack_buff_stacks -= 1
            buff = config.apply_stack_decay(defender.attack_buff_stacks)
            self.log(f"✋ {attacker.name} gets a Steal! {defender.name}'s attack lowered to {buff:.2f}.")
        elif action_type == 'block':
            # --- Rim Protector Bonus ---
            stacks = 1
            if 'Rim Protector' in attacker.labels:
                stacks = 2
                self.log(f"🛡️ {attacker.name}'s Rim Protector Bonus! -1 Extra Def Stack") 
            defender.defense_buff_stacks -= stacks
            buff = config.apply_stack_decay(defender.defense_buff_stacks)
            self.log(f"🚫 {attacker.name} gets a Block! {defender.name}'s defense lowered to {buff:.2f}.")

    def resolve_attack(self, attacker, defender):
        if not attacker.attack_pool:
            outcome = 'regular'
        else:
            outcome = random.choice(attacker.attack_pool)
            
        if outcome == 'miss':
            self.log(f"🧱 {attacker.name} shoots at {defender.name}... MISS! (0 Damage)")
            return
            
        atk_val = attacker.attack * config.apply_stack_decay(attacker.attack_buff_stacks)
        def_val = defender.defense * config.apply_stack_decay(defender.defense_buff_stacks)
        
        damage = config.calculate_damage(atk_val, def_val, outcome if outcome != 'regular' else 'regular')
        
        if 'Microwave' in attacker.labels and not attacker.microwave_used:
            damage *= 2
            attacker.microwave_used = True
            self.log("🔥 {attacker.name}'s Microwave activated! Double Damage!")
            
        defender.current_hp = max(0, defender.current_hp - damage)
        
        desc = "Field Goal"
        if outcome == 'strong': desc = "3-Pointer"
        elif outcome == 'weak': desc = "Free Throw"
        
        self.log(f"💥 {attacker.name} scores a {desc} on {defender.name}! Deals {damage:.1f} damage.")
        attacker.attack_buff_stacks = 0
        defender.defense_buff_stacks = 0

class Battle5v5:
    """
    Manages a 5v5 Coach Mode Battle
    - Broken into 4 Quarters
    - User selects Strategy every quarter
    - Simulation runs automatically based on strategy weights
    """
    
    def __init__(self, team1_units, team2_units):
        self.team1 = team1_units
        self.team2 = team2_units
        self.quarter = 1
        self.battle_log = []
        
        self.team1_timeouts = 2
        self.team2_timeouts = 2
        
        # Default Strategies
        self.team1_strat = {'off': 'Feed the Hot Hand', 'def': 'Switch Everything'}
        self.team2_strat = {'off': 'Ball Movement', 'def': 'Box Out'}
        
        # Determine Initiatives
        self.rank_initiative = []
        for i in range(5):
            if i < len(team1_units) and i < len(team2_units):
                if team1_units[i].plus_minus >= team2_units[i].plus_minus:
                    self.rank_initiative.append(1)
                else:
                    self.rank_initiative.append(2)
            else:
                self.rank_initiative.append(1)

        # Apply stopper label effects across teams
        self.apply_stopper_effects()
        # Strategy state tracking (for Ball Movement chain logic)
        self.team1_assist_chain = 0
        self.team2_assist_chain = 0

    def apply_stopper_effects(self):
        # Apply Stopper label: each Stopper adds 2 misses to their lane opponent
        for i in range(5):
            if i < len(self.team1) and i < len(self.team2):
                # Team1 stopper affects Team2 opponent
                if 'Stopper' in self.team1[i].labels:
                    self.team2[i].attack_pool.append('miss')
                    self.team2[i].attack_pool.append('miss')
                # Team2 stopper affects Team1 opponent
                if 'Stopper' in self.team2[i].labels:
                    self.team1[i].attack_pool.append('miss')
                    self.team1[i].attack_pool.append('miss')


    def log(self, message):
        print(message)
        self.battle_log.append(message)

    def execute_battle(self):
        self.log(f"\n{'='*60}")
        self.log(f"5v5 COACH MODE BATTLE START")
        self.log(f"{'='*60}\n")
        
        while self.quarter <= 4 and self.team_alive(self.team1) and self.team_alive(self.team2):
            self.play_quarter()
            if self.team_alive(self.team1) and self.team_alive(self.team2):
                self.quarter += 1
        
        # Check for OVERTIME trigger (Tied survivors)
        t1_alive = sum(1 for u in self.team1 if u.is_alive())
        t2_alive = sum(1 for u in self.team2 if u.is_alive())
        
        if t1_alive > 0 and t2_alive > 0 and t1_alive == t2_alive:
            self.log(f"\n⚡ REGULATION ENDED IN A DRAW! ({t1_alive} vs {t2_alive} survivors)")
            self.log(f"⚡ ENTERING SUDDEN DEATH OVERTIME (1v1)")
            return self.resolve_overtime()
        
        # Normal End
        winner = 1 if t1_alive > t2_alive else 2
        if t1_alive == 0 and t2_alive > 0: winner = 2
        elif t2_alive == 0 and t1_alive > 0: winner = 1
        
        survivors = t1_alive if winner == 1 else t2_alive
        
        self.log(f"\n{'='*60}")
        self.log(f"GAME OVER! TEAM {winner} WINS!")
        self.log(f"Survivors: {survivors}")
        self.log(f"{'='*60}\n")
        
        self.display_team_status()

        return {'winning_team': winner, 'survivors': survivors}

    def resolve_overtime(self):
        """Run a 1v1 battle with the first available players from each team"""
        # Find champions (first living unit)
        p1 = next((u for u in self.team1 if u.is_alive()), None)
        p2 = next((u for u in self.team2 if u.is_alive()), None)
        
        if not p1 or not p2:
            # Fallback if logic fails (should be impossible due to check above)
            return {'winning_team': 1, 'survivors': 1}
            
        self.log(f"\n⚔️  OVERTIME DUEL: {p1.name} vs {p2.name} ⚔️")
        self.log(f"HP: {math.ceil(p1.current_hp)} vs {math.ceil(p2.current_hp)}")
        input("Press Enter to begin Overtime...")
        
        # Create interactive battle instance
        
        ot_battle = Battle(p1, p2)
        result = ot_battle.execute_battle()
        
        winner_team = 1 if result['winner'] == p1 else 2
        
        return {'winning_team': winner_team, 'survivors': 1}

    def play_quarter(self):
        self.log(f"\n🏀 --- QUARTER {self.quarter} START --- 🏀")
        self.display_team_status()
        
        # 1. Strategy Phase
        self.choose_strategy()
        
        # 2. Simulation Loop (approx 12 rounds per quarter)
        rounds_to_play = 12
        
        for r in range(rounds_to_play):
            if not self.team_alive(self.team1) or not self.team_alive(self.team2): break
            
            # self.log(f"--- Q{self.quarter} | Round {r+1} ---")
            
            for rank in range(5):
                # Init check
                if self.rank_initiative[rank] == 1:
                    self.sim_lane_action(self.team1, self.team2, rank, 1, self.team1_strat)
                    self.sim_lane_action(self.team2, self.team1, rank, 2, self.team2_strat)
                else:
                    self.sim_lane_action(self.team2, self.team1, rank, 2, self.team2_strat)
                    self.sim_lane_action(self.team1, self.team2, rank, 1, self.team1_strat)

    def choose_strategy(self):
        print("\n📋 COACH'S CLIPBOARD")
        print("Choose Offensive Strategy:")
        off_opts = ["Feed the Hot Hand", "Ball Movement", "Crash the Glass", "7 Seconds or Less"]
        for i, o in enumerate(off_opts): print(f"{i+1}. {o}")
        
        try:
            o_choice = int(input("Select Offense (1-4): ")) - 1
            if 0 <= o_choice < 4: self.team1_strat['off'] = off_opts[o_choice]
        except: pass
        
        print("\nChoose Defensive Strategy:")
        def_opts = ["Lockdown Paint", "Full Court Press", "Box Out", "Switch Everything"]
        for i, o in enumerate(def_opts): print(f"{i+1}. {o}")
        
        try:
            d_choice = int(input("Select Defense (1-4): ")) - 1
            if 0 <= d_choice < 4: self.team1_strat['def'] = def_opts[d_choice]
        except: pass
        
        # Randomize AI Strat
        self.team2_strat['off'] = random.choice(off_opts)
        self.team2_strat['def'] = random.choice(def_opts)
        
        print(f"\nStrategies Set: {self.team1_strat['off']} / {self.team1_strat['def']}")
        input("Press Enter to begin Quarter...")

    def sim_lane_action(self, atk_team, def_team, rank, team_num, strat):
        if rank >= len(atk_team): return
        attacker = atk_team[rank]
        if not attacker.is_alive(): return
        
        # Refill check
        if attacker.deck_is_empty():
            attacker.refill_deck(0.25)
            
        # Select Action Weighted by Strategy
        action = self.weighted_action_choice(attacker, strat, atk_team, team_num)
        if not action: return # No valid moves
        
        attacker.action_deck[action] -= 1
        
        # Target
        target = None
        if rank < len(def_team) and def_team[rank].is_alive():
            target = def_team[rank]
        else:
            # Spill over
            alive = [u for u in def_team if u.is_alive()]
            if alive: target = random.choice(alive)
            
        if not target and action != 'offensive_rebound': return

        # Resolve
        if action == 'attack':
            self.resolve_attack_5v5(attacker, target, team_num)
            # Reset assist chain after attack (Ball Movement strategy)
            if team_num == 1:
                self.team1_assist_chain = 0
            else:
                self.team2_assist_chain = 0
            
        elif action == 'offensive_rebound':
            allies = [u for u in atk_team if u.is_alive()]
            if allies:
                # Heal most damaged
                heal_target = min(allies, key=lambda x: x.current_hp/x.max_hp)
                amt = heal_target.max_hp * 0.15
                heal_target.current_hp = min(heal_target.max_hp, heal_target.current_hp + amt)
                self.log(f"T{team_num} {attacker.name} grabs O-REB! Heals {heal_target.name} (+{amt:.0f} HP)")
                
        elif action == 'assist':
            stacks = 1
            # --- Floor General Bonus ---
            if 'Floor General' in attacker.labels:
                stacks = 2
                # self.log(f"🧠 Floor General Bonus! +1 Extra Stack")
            # Synergy: Buff NEXT ally
            next_rank = (rank + 1) % 5
            ally = atk_team[next_rank]
            if ally.is_alive():
                ally.attack_buff_stacks += stacks
                self.log(f"T{team_num} {attacker.name} Assists -> Buffs {ally.name} (Atk +{ally.attack_buff_stacks} stacks)")
            else:
                # If next is dead, find first alive
                found = False
                for i in range(5):
                    if atk_team[i].is_alive() and i != rank:
                        atk_team[i].attack_buff_stacks += 1
                        self.log(f"T{team_num} {attacker.name} Assists -> Buffs {atk_team[i].name} (Atk +{atk_team[i].attack_buff_stacks} stacks)")
                        found = True
                        break
            
            # Track assist chain for Ball Movement strategy
            if team_num == 1:
                self.team1_assist_chain += 1
            else:
                self.team2_assist_chain += 1

        
        elif action == 'steal':
            target.attack_buff_stacks -= 1
            self.log(f"T{team_num} {attacker.name} steals from {target.name} (Atk {target.attack_buff_stacks} stacks)")
            
        elif action == 'block':
            # --- Rim Protector Bonus ---
            stacks = 1
            if 'Rim Protector' in attacker.labels:
                stacks = 2
                # self.log(f"🧠 Rim Protector Bonus! +1 Extra Stack")
            target.defense_buff_stacks -= stacks
            self.log(f"T{team_num} {attacker.name} blocks {target.name} (Def {target.defense_buff_stacks} stacks)")
            
        elif action == 'defensive_rebound':
            attacker.defense_buff_stacks += 1
            self.log(f"T{team_num} {attacker.name} grabs D-REB (Def +{attacker.defense_buff_stacks} stacks)")

    def weighted_action_choice(self, unit, strat, atk_team, team_num):
        """Pick action based on deck availability AND Strategy weights"""
        available = [k for k, v in unit.action_deck.items() if v > 0]
        if not available: return None
        
        weights = {k: 1.0 for k in available}
        
        # Get chain count for this team
        if team_num == 1:
            chain_count = self.team1_assist_chain
        else:
            chain_count = self.team2_assist_chain
        
        # Apply Offensive Strategy Weights
        off = strat['off']
        
        if off == "Feed the Hot Hand":
            # Identify star player (highest attack on team)
            alive_teammates = [u for u in atk_team if u.is_alive()]
            if alive_teammates:
                star = max(alive_teammates, key=lambda u: u.attack)
                if unit == star:
                    # Star: heavily favor attacking
                    if 'attack' in weights: weights['attack'] *= 5.0
                    # Suppress support actions for the star
                    if 'assist' in weights: weights['assist'] *= 0.3
                    if 'offensive_rebound' in weights: weights['offensive_rebound'] *= 0.5
                else:
                    # Role players: heavily favor assists to feed the star
                    if 'assist' in weights: weights['assist'] *= 4.0
                    # Suppress attacks for role players
                    if 'attack' in weights: weights['attack'] *= 0.3
                    
        elif off == "Ball Movement":
            # Chain assists before attacking
            if chain_count < 2:
                # Need more assists - suppress attacks until chain is built
                if 'assist' in weights: weights['assist'] *= 5.0
                if 'attack' in weights: weights['attack'] *= 0.2
            else:
                # Chain built - now favor attacks to cash in the buffs
                if 'attack' in weights: weights['attack'] *= 4.0
                if 'assist' in weights: weights['assist'] *= 0.5
                
        elif off == "Crash the Glass":
            if 'offensive_rebound' in weights: weights['offensive_rebound'] *= 4.0
            
        elif off == "7 Seconds or Less":
            # Aggressive: heavily favor attacks, suppress setup actions
            if 'attack' in weights: weights['attack'] *= 5.0
            if 'assist' in weights: weights['assist'] *= 0.3
            if 'defensive_rebound' in weights: weights['defensive_rebound'] *= 0.3
            if 'offensive_rebound' in weights: weights['offensive_rebound'] *= 0.5
            
        # Apply Defensive Strategy Weights
        defn = strat['def']
        if defn == "Lockdown Paint":
            if 'block' in weights: weights['block'] *= 3.0
        elif defn == "Full Court Press":
            if 'steal' in weights: weights['steal'] *= 3.0
        elif defn == "Box Out":
            if 'defensive_rebound' in weights: weights['defensive_rebound'] *= 3.0
            
        # Select
        try:
            choices = list(weights.keys())
            probs = list(weights.values())
            return random.choices(choices, weights=probs, k=1)[0]
        except:
            return random.choice(available)

    def resolve_attack_5v5(self, attacker, target, team_num):
        pool = attacker.attack_pool if attacker.attack_pool else ['regular']
        atype = random.choice(pool)
        
        if atype == 'miss':
            self.log(f"T{team_num} {attacker.name} misses shot on {target.name}.")
            return
            
        atk = attacker.attack * config.apply_stack_decay(attacker.attack_buff_stacks)
        defn = target.defense * config.apply_stack_decay(target.defense_buff_stacks)
        dmg = config.calculate_damage(atk, defn, atype if atype != 'regular' else 'regular')
        
        target.current_hp = max(0, target.current_hp - dmg)
        self.log(f"T{team_num} {attacker.name} scores on {target.name}! ({dmg:.0f} dmg)")
        
        # Reset
        attacker.attack_buff_stacks = 0
        target.defense_buff_stacks = 0

    def team_alive(self, team):
        return any(u.is_alive() for u in team)

    def display_team_status(self):
        print("\n--- TEAM STATUS ---")
        print("YOUR TEAM:")
        for u in self.team1:
            status = f"{math.ceil(u.current_hp)}/{math.ceil(u.max_hp)} HP" if u.is_alive() else "OUT"
            print(f"  {u.name}: {status}")
        print("OPPONENT TEAM:")
        for u in self.team2:
            status = f"{math.ceil(u.current_hp)}/{math.ceil(u.max_hp)} HP" if u.is_alive() else "OUT"
            print(f"  {u.name}: {status}")