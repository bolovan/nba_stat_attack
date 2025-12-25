"""
Game Manager
Handles user inventory, token economy, and overall game progression
"""

import json
import os
import random
from datetime import datetime
import game_config as config
import nba_data
import battle_engine

class GameManager:
    def __init__(self):
        self.nba_manager = nba_data.NBADataManager()
        self.save_file = 'game_save.json'
        
        self.game_state = {
            'tokens': 0,
            'total_wins': 0,
            # Card ID format: "PLAYERID_SEASON" (e.g., "2544_2016-17")
            'player_cards': [],  
            'player_records': {},  
            'gametapes': {},  
            'gametape_records': {},  
            'gametape_metadata': {}, 
            'hall_of_fame': [],
            'created_date': datetime.now().isoformat()
        }
        
        if self.load_game():
            self.verify_and_repair_save()
        else:
            self.new_game()

    # --- HELPERS ---
    def parse_card_id(self, card_id):
        """Extract player_id and season from composite ID"""
        try:
            parts = card_id.split('_')
            return int(parts[0]), parts[1]
        except:
            return None, None

    def get_player_name(self, card_id):
        """Get display name including season"""
        pid, season = self.parse_card_id(card_id)
        if not pid: return "Unknown"
        
        try:
            cursor = self.nba_manager.conn.cursor()
            cursor.execute("SELECT full_name FROM players WHERE id=?", (pid,))
            row = cursor.fetchone()
            name = row['full_name'] if row else f"Player {pid}"
            return f"{name} ({season})"
        except:
            return f"Player {pid} ({season})"

    # --- SAVE SYSTEM ---
    def load_game(self):
        """Load game from session state (browser-based, per-user)"""
        try:
            import streamlit as st
            if 'saved_game_data' in st.session_state:
                self.game_state.update(st.session_state['saved_game_data'])
                return True
            return False
        except Exception:
            return False

    def save_game(self):
        """Save game to session state (browser-based, per-user)"""
        try:
            import streamlit as st
            st.session_state['saved_game_data'] = self.game_state.copy()
        except Exception:
            pass

    def verify_and_repair_save(self):
        """Repair metadata for tapes"""
        # print("Verifying save data integrity...") 
        dirty = False
        
        for card_id, tapes in self.game_state['gametapes'].items():
            pid, season = self.parse_card_id(card_id)
            if not pid: continue
            
            for tape_id in tapes:
                if tape_id not in self.game_state.get('gametape_metadata', {}):
                    try:
                        # Regenerate name
                        game_id = tape_id.split('_')[1]
                        games = self.nba_manager.get_player_games(pid, season)
                        stats = self.nba_manager.get_player_season_stats(pid, season)
                        
                        target_game = next((g for g in games if str(g['game_id']) == str(game_id)), None)
                        
                        if target_game and stats:
                            labels = self.nba_manager.detect_gametape_labels_offline(pid, game_id, target_game)
                            name = self.create_gametape_display_name(target_game, stats, labels)
                            self.game_state['gametape_metadata'][tape_id] = name
                            dirty = True
                    except:
                        pass
        if dirty:
            self.save_game()

    # --- GAME START ---
    def new_game(self):
        print("\n🏀 Welcome to NBA Stat Attack! 🏀")
        print("Initializing new game...")
        try:
            self.give_random_starter()
        except Exception as e:
            print(f"Error generating starter: {e}")
        self.save_game()

    def give_random_starter(self):
        print("\nSelecting starter...")
        pool = self.nba_manager.get_available_card_pool()
        
        valid_starters = random.sample(pool, min(50, len(pool)))
        
        for candidate in valid_starters:
            pid = candidate['id']
            season = candidate['season']
            
            stats = self.nba_manager.get_player_season_stats(pid, season)
            if not stats: continue
            
            games = self.nba_manager.get_player_games(pid, season)
            if not games: continue
            
            # Find valid tape
            for game in games[:5]:
                # Calculate labels here to include in name immediately
                moves_data = self.nba_manager.get_game_moves(pid, game['game_id'], calculate_labels=True)
                valid, _ = self.nba_manager.validate_gametape(moves_data, game)
                if valid:
                    # Found one!
                    card_id = f"{pid}_{season}"
                    tape_id = f"{pid}_{game['game_id']}"
                    
                    self.game_state['player_cards'].append(card_id)
                    self.game_state['gametapes'][card_id] = [tape_id]
                    self.game_state['player_records'][card_id] = {'wins': 0, 'losses': 0}
                    self.game_state['gametape_records'][tape_id] = {'wins': 0, 'losses': 0}
                    
                    # Metadata with labels
                    name = self.create_gametape_display_name(game, stats, moves_data.get('labels', []))
                    self.game_state['gametape_metadata'][tape_id] = name
                    
                    print(f"🎉 Starter: {candidate['full_name']} ({season})")
                    print(f"Tape: {name}")
                    return

    # --- CORE LOGIC ---
    def create_gametape_display_name(self, game_stats, season_stats, labels):
        """Format: YYYYMMDD_Matchup_Stats_Labels"""
        date_str = game_stats.get('date', game_stats.get('game_date', '0000-00-00'))
        fmt_date = date_str.replace('-', '')
        matchup = game_stats['matchup'].replace(' @ ', 'vs').replace(' vs. ', 'vs')
        
        # Add labels to display string
        label_str = ""
        if labels and len(labels) > 0:
            label_str = f" [{', '.join(labels)}]"
        
        return f"{fmt_date}_{matchup} [{game_stats['pts']}P/{game_stats['reb']}R/{game_stats['ast']}A]{label_str}"

    def create_battle_unit(self, card_id, tape_id, calculate_labels=True):
        pid, season = self.parse_card_id(card_id)
        if not pid: return None
        
        # 1. Get Player Season Stats
        season_stats = self.nba_manager.get_player_season_stats(pid, season)
        if not season_stats: return None
        
        # 2. Get Game Stats
        try:
            game_id = tape_id.split('_')[1]
        except: return None
        
        games = self.nba_manager.get_player_games(pid, season)
        game_stats = next((g for g in games if str(g['game_id']) == str(game_id)), None)
        if not game_stats: return None
        
        # 3. Get Moves & Labels
        moves_data = self.nba_manager.get_game_moves(pid, game_id, calculate_labels=calculate_labels)
        
        # 4. Construct Unit
        player_card_mock = {
            'id': pid,
            'full_name': self.get_player_name(card_id) 
        }
        
        gametape = {
            'game_id': game_id,
            'game_stats': game_stats,
            'moves': moves_data
        }
        unit = battle_engine.BattleUnit(player_card_mock, gametape, season_stats)
    
        # Attach extra attributes for UI access
        unit.season_stats = season_stats
        unit.gametape = gametape
        
        return unit


    # --- SHOP LOGIC FOR STREAMLIT ---
    def buy_gametape_logic(self, card_id):
        """Logic to buy a gametape for a specific player (used by UI)"""
        pid, season = self.parse_card_id(card_id)
        games = self.nba_manager.get_player_games(pid, season)
        
        if not games:
            return False, "No games found for this player."
            
        for _ in range(20):
            g = random.choice(games)
            tid = f"{pid}_{g['game_id']}"
            
            if tid in self.game_state['gametapes'].get(card_id, []):
                continue
            
            m = self.nba_manager.get_game_moves(pid, g['game_id'], calculate_labels=True)
            if self.nba_manager.validate_gametape(m, g)[0]:
                # Purchase
                self.game_state['tokens'] -= config.GAMETAPE_COST
                if card_id not in self.game_state['gametapes']:
                    self.game_state['gametapes'][card_id] = []
                self.game_state['gametapes'][card_id].append(tid)
                self.game_state['gametape_records'][tid] = {'wins': 0, 'losses': 0}
                
                stats = self.nba_manager.get_player_season_stats(pid, season)
                tname = self.create_gametape_display_name(g, stats, m.get('labels', []))
                self.game_state['gametape_metadata'][tid] = tname
                
                self.save_game()
                return True, tname
                
        return False, "Could not find a valid new gametape."

    # --- MENUS (Legacy Console Support) ---
    def battle_menu(self):
        print("\n⚔️  BATTLE MENU ⚔️")
        print("1. Quick Battle (1v1)")
        
        wins = self.game_state['total_wins']
        valid_roster_count = sum(1 for cid in self.game_state['player_cards'] 
                               if len(self.game_state['gametapes'].get(cid, [])) > 0)
        
        can_5v5 = (wins >= config.GAMES_TO_UNLOCK_5V5) and (valid_roster_count >= 5)
        reason = ""
        if wins < config.GAMES_TO_UNLOCK_5V5: reason = f"Need {config.GAMES_TO_UNLOCK_5V5} wins"
        elif valid_roster_count < 5: reason = "Need 5 players with tapes"
        
        if can_5v5: print("2. Team Battle (5v5)")
        else: print(f"2. Team Battle (LOCKED: {reason})")
        print("3. Back")
        
        choice = config.get_valid_input("Choice: ", 3)
        if choice == 1: self.quick_battle()
        elif choice == 2:
            if can_5v5: self.team_battle()
            else: print("Locked!"); input("...")

    def quick_battle(self):
        print("\nYour Roster:")
        for i, cid in enumerate(self.game_state['player_cards']):
            rec = self.game_state['player_records'].get(cid, {'wins':0, 'losses':0})
            print(f"{i+1}. {self.get_player_name(cid)} [W{rec['wins']}-L{rec['losses']}]")
            
        if not self.game_state['player_cards']: return
        c_idx = config.get_valid_input("Select: ", len(self.game_state['player_cards'])) - 1
        card_id = self.game_state['player_cards'][c_idx]
        
        tapes = self.game_state['gametapes'].get(card_id, [])
        if not tapes: print("No tapes!"); return
        
        print("\nSelect Gametape:")
        for i, tid in enumerate(tapes):
            rec = self.game_state['gametape_records'].get(tid, {'wins':0, 'losses':0})
            meta = self.get_display_name(tid)
            print(f"{i+1}. {meta} [W{rec['wins']}-L{rec['losses']}]")
            
        t_idx = config.get_valid_input("Select: ", len(tapes)) - 1
        tape_id = tapes[t_idx]
        
        p_unit = self.create_battle_unit(card_id, tape_id, calculate_labels=True)
        if not p_unit: print("Error creating unit"); return
        
        print("\nFinding opponent...")
        o_unit = self.generate_random_opponent()
        if not o_unit: print("Error generating opponent"); return
        
        o_tape_name = self.create_gametape_display_name(
            o_unit.gametape['game_stats'], 
            o_unit.season_stats, 
            o_unit.labels
        )
        print("\n" + "="*40)
        print("TALE OF THE TAPE")
        print(f"YOU: {p_unit.name}")
        print(f"     PWR: {p_unit.power_rating} | +/-: {p_unit.plus_minus}")
        print(f"OPP: {o_unit.name}")
        print(f"     PWR: {o_unit.power_rating} | +/-: {o_unit.plus_minus}")
        print(f"     TAPE: {o_tape_name}")
        print("="*40)
        input("Press Enter to FIGHT...")
        
        battle = battle_engine.Battle(p_unit, o_unit)
        res = battle.execute_battle()
        
        self.handle_battle_result(res, p_unit, tape_id, card_id)

    def team_battle(self):
        valid_roster = [cid for cid in self.game_state['player_cards'] 
                        if self.game_state['gametapes'].get(cid)]
        
        team_units = []
        selected_info = [] 
        
        print("\nSelect 5 Players for your Lineup:")
        for slot in range(5):
            print(f"\nSlot {slot+1}:")
            for i, cid in enumerate(valid_roster):
                if cid in [x[0] for x in selected_info]: continue 
                print(f"{i+1}. {self.get_player_name(cid)}")
            
            c_idx = config.get_valid_input("Select Player: ", len(valid_roster)) - 1
            cid = valid_roster[c_idx]
            
            tapes = self.game_state['gametapes'][cid]
            for i, tid in enumerate(tapes):
                print(f"{i+1}. {self.get_display_name(tid)}")
            t_idx = config.get_valid_input("Select Tape: ", len(tapes)) - 1
            tid = tapes[t_idx]
            
            unit = self.create_battle_unit(cid, tid)
            if unit:
                team_units.append(unit)
                selected_info.append((cid, tid))
        
        print("\nGenerating Opponent Team...")
        opp_units = [self.generate_random_opponent() for _ in range(5)]
        opp_units = [u for u in opp_units if u]
        if len(opp_units) < 5: print("Error gen opponents"); return
        
        print("\n" + "="*40)
        print("5v5 MATCHUP")
        print("YOUR TEAM vs OPPONENT TEAM")
        for i in range(5):
            print(f"{team_units[i].name} vs {opp_units[i].name}")
        print("="*40)
        input("Press Enter to FIGHT...")
        
        battle = battle_engine.Battle5v5(team_units, opp_units)
        res = battle.execute_battle()
        
        win = (res['winning_team'] == 1)
        
        if win:
            print("\n🏆 VICTORY!")
            self.game_state['tokens'] += config.TOKENS_WIN_5V5
            self.game_state['total_wins'] += 1
            for cid, tid in selected_info:
                self.game_state['player_records'][cid]['wins'] += 1
                self.game_state['gametape_records'][tid]['wins'] += 1
        else:
            print("\n💀 DEFEAT")
            self.game_state['tokens'] += config.TOKENS_LOSE_5V5
            for cid, tid in selected_info:
                self.game_state['player_records'][cid]['losses'] += 1
                self.game_state['gametape_records'][tid]['losses'] += 1
        
        for cid, tid in selected_info:
            self.check_retirement(tid, cid)
            
        self.save_game()
        input("Press Enter...")

    def handle_battle_result(self, res, unit, tape_id, card_id):
        if res['winner'] == unit:
            print("\n🏆 VICTORY!")
            self.game_state['tokens'] += config.TOKENS_WIN_1V1
            self.game_state['total_wins'] += 1
            self.game_state['player_records'][card_id]['wins'] += 1
            self.game_state['gametape_records'][tape_id]['wins'] += 1
        else:
            print("\n💀 DEFEAT")
            self.game_state['tokens'] += config.TOKENS_LOSE_1V1
            self.game_state['player_records'][card_id]['losses'] += 1
            self.game_state['gametape_records'][tape_id]['losses'] += 1
            
        self.check_retirement(tape_id, card_id)
        self.save_game()
        input("Press Enter...")

    def check_retirement(self, tape_id, card_id):
        rec = self.game_state['gametape_records'][tape_id]
        player_name = self.get_player_name(card_id)
        
        if rec['wins'] >= config.GAMETAPE_MAX_WINS:
            print(f"🌟 LEGENDARY! {player_name}'s {self.get_display_name(tape_id)} has entered the Hall of Fame!")
            self.game_state['hall_of_fame'].append(tape_id)
            self.game_state['gametapes'][card_id].remove(tape_id)
            self.game_state['tokens'] += config.GAMETAPE_RETIREMENT_BONUS
        elif rec['losses'] >= config.GAMETAPE_MAX_LOSSES:
            print(f"📉 CUT! {player_name}'s {self.get_display_name(tape_id)} has been sent to the G-League (Removed).")
            self.game_state['gametapes'][card_id].remove(tape_id)

    def generate_random_opponent(self):
        pool = self.nba_manager.get_available_card_pool()
        for _ in range(20):
            cand = random.choice(pool)
            pid = cand['id']
            season = cand['season']
            
            stats = self.nba_manager.get_player_season_stats(pid, season)
            if not stats: continue
            
            games = self.nba_manager.get_player_games(pid, season)
            if not games: continue
            
            game = random.choice(games[:10])
            moves_data = self.nba_manager.get_game_moves(pid, game['game_id'], calculate_labels=True)
            valid, _ = self.nba_manager.validate_gametape(moves_data, game)
            
            if valid:
                gametape = {'game_id': game['game_id'], 'game_stats': game, 'moves': moves_data}
                
                card_mock = {'id': pid, 'full_name': f"{cand['full_name']} ({season})"}
                
                unit = battle_engine.BattleUnit(card_mock, gametape, stats)
                unit.season_stats = stats
                unit.gametape = gametape
                return unit
        return None

    def shop_menu(self):
        print(f"\n🛒 SHOP | Tokens: {self.game_state['tokens']}")
        print(f"1. Buy Tape ({config.GAMETAPE_COST})")
        print(f"2. Buy Player ({config.PLAYER_CARD_COST})")
        print("3. Sell")
        print("4. Back")
        
        choice = config.get_valid_input("Choice: ", 4)
        if choice == 1: self.buy_gametape()
        elif choice == 2: self.buy_player_card()
        elif choice == 3: self.sell_menu()

    def buy_player_card(self):
        if self.game_state['tokens'] < config.PLAYER_CARD_COST: print("Not enough tokens"); return
        
        pool = self.nba_manager.get_available_card_pool()
        for _ in range(50):
            cand = random.choice(pool)
            card_id = f"{cand['id']}_{cand['season']}"
            
            if card_id in self.game_state['player_cards']: continue
            
            stats = self.nba_manager.get_player_season_stats(cand['id'], cand['season'])
            if not stats: continue
            
            games = self.nba_manager.get_player_games(cand['id'], cand['season'])
            valid_tape = None
            for g in random.sample(games, min(5, len(games))):
                # Calculate labels at purchase time
                m = self.nba_manager.get_game_moves(cand['id'], g['game_id'], calculate_labels=True)
                if self.nba_manager.validate_gametape(m, g)[0]:
                    valid_tape = g
                    # Capture labels for display name
                    valid_labels = m.get('labels', [])
                    break
            
            if valid_tape:
                self.game_state['tokens'] -= config.PLAYER_CARD_COST
                self.game_state['player_cards'].append(card_id)
                self.game_state['player_records'][card_id] = {'wins':0, 'losses':0}
                
                tid = f"{cand['id']}_{valid_tape['game_id']}"
                self.game_state['gametapes'][card_id] = [tid]
                self.game_state['gametape_records'][tid] = {'wins':0, 'losses':0}
                
                # Pass captured labels to name generator
                tname = self.create_gametape_display_name(valid_tape, stats, valid_labels)
                self.game_state['gametape_metadata'][tid] = tname
                
                print(f"✅ Purchased: {cand['full_name']} ({cand['season']})")
                self.save_game()
                return
        print("Could not find valid player.")

    def buy_gametape(self):
        if self.game_state['tokens'] < config.GAMETAPE_COST: print("Not enough tokens"); return
        
        print("Select Player:")
        for i, cid in enumerate(self.game_state['player_cards']):
            print(f"{i+1}. {self.get_player_name(cid)}")
        
        idx = config.get_valid_input("Choice: ", len(self.game_state['player_cards'])) - 1
        card_id = self.game_state['player_cards'][idx]
        pid, season = self.parse_card_id(card_id)
        
        games = self.nba_manager.get_player_games(pid, season)
        for _ in range(20):
            g = random.choice(games)
            tid = f"{pid}_{g['game_id']}"
            if tid in self.game_state['gametapes'][card_id]: continue
            
            # Calculate labels at purchase time
            m = self.nba_manager.get_game_moves(pid, g['game_id'], calculate_labels=True)
            if self.nba_manager.validate_gametape(m, g)[0]:
                self.game_state['tokens'] -= config.GAMETAPE_COST
                self.game_state['gametapes'][card_id].append(tid)
                self.game_state['gametape_records'][tid] = {'wins':0, 'losses':0}
                
                stats = self.nba_manager.get_player_season_stats(pid, season)
                tname = self.create_gametape_display_name(g, stats, m.get('labels', []))
                self.game_state['gametape_metadata'][tid] = tname
                
                print(f"✅ Bought Tape: {tname}")
                self.save_game()
                return
        print("No new valid tapes found for this player/season.")

    def sell_menu(self):
        print("\nWhat to sell?")
        print("1. Gametape")
        print("2. Player")
        choice = config.get_valid_input("Choice: ", 2)
        if choice == 1: self.sell_gametape()
        elif choice == 2: self.sell_player()

    def sell_gametape(self):
        all_tapes = []
        for pid, tapes in self.game_state['gametapes'].items():
            for tid in tapes: all_tapes.append((pid, tid))
            
        for i, (pid, tid) in enumerate(all_tapes):
            player_name = self.get_player_name(pid)
            tape_name = self.get_display_name(tid)
            print(f"{i+1}. {player_name} - {tape_name}")
            
        choice = config.get_valid_input("Sell which? ", len(all_tapes)) - 1
        pid, tid = all_tapes[choice]
        
        self.game_state['gametapes'][pid].remove(tid)
        self.game_state['tokens'] += config.GAMETAPE_SELL_VALUE
        print("Sold!")
        self.save_game()

    def sell_player(self):
        if len(self.game_state['player_cards']) <= 1:
            print("Must keep one player!")
            return
        
        for i, pid in enumerate(self.game_state['player_cards']):
            print(f"{i+1}. {self.get_player_name(pid)}")
            
        choice = config.get_valid_input("Sell which? ", len(self.game_state['player_cards'])) - 1
        pid = self.game_state['player_cards'][choice]
        
        self.game_state['player_cards'].remove(pid)
        count = len(self.game_state['gametapes'].get(pid, []))
        if pid in self.game_state['gametapes']:
            del self.game_state['gametapes'][pid]
            
        total = config.PLAYER_CARD_SELL_VALUE + (count * config.GAMETAPE_SELL_VALUE)
        self.game_state['tokens'] += total
        print(f"Sold for {total} tokens")
        self.save_game()

    def view_roster(self):
        while True:
            print("\n📋 ROSTER")
            print(f"Total Wins: {self.game_state['total_wins']} / {config.GAMES_TO_UNLOCK_5V5} for Team Battle")
            
            for i, pid in enumerate(self.game_state['player_cards']):
                p = self.get_player_name(pid)
                print(f"{i+1}. {p}")
                for tid in self.game_state['gametapes'].get(pid, []):
                    rec = self.get_tape_record_str(tid)
                    # FIX: Use saved metadata
                    print(f"    - {self.get_display_name(tid)} {rec}")
            
            print("\nOptions:")
            print("P. Preview Gametape Moves")
            print("B. Back to Main Menu")
            choice = input("Choice: ").upper()
            
            if choice == 'B':
                break
            elif choice == 'P':
                self.preview_gametape_content()

    def preview_gametape_content(self):
        print("\nSelect player to preview:")
        for i, pid in enumerate(self.game_state['player_cards']):
            p = self.get_player_name(pid)
            print(f"{i+1}. {p}")
        
        choice = config.get_valid_input("Choice: ", len(self.game_state['player_cards'])) - 1
        pid = self.game_state['player_cards'][choice]
        
        gametapes = self.game_state['gametapes'].get(pid, [])
        if not gametapes:
            print("No tapes to preview.")
            return

        print("\nSelect gametape:")
        for i, tid in enumerate(gametapes):
            # FIX: Use saved metadata
            print(f"{i+1}. {self.get_display_name(tid)}")
            
        choice = config.get_valid_input("Choice: ", len(gametapes)) - 1
        tid = gametapes[choice]
        
        game_id = tid.split('_')[1]
        player_id = tid.split('_')[0]
        moves_data = self.nba_manager.get_game_moves(player_id, game_id, calculate_labels=False)
        
        if not moves_data or not moves_data.get('moves'):
            print("Error fetching moves.")
            return

        moves = moves_data['moves']
        counts = {}
        for m in moves:
            t = m['type']
            counts[t] = counts.get(t, 0) + 1
            
        print(f"\n📺 PREVIEW: {self.get_display_name(tid)}")
        print(f"Total Moves: {len(moves)}")
        print("-" * 30)
        for mtype, count in counts.items():
            print(f"{mtype.replace('_', ' ').title()}: {count}")
        print("-" * 30)
        input("Press Enter to return...")

    def get_display_name(self, gametape_id):
        """Get display name from metadata or fallback to ID"""
        return self.game_state.get('gametape_metadata', {}).get(gametape_id, gametape_id)

    def get_tape_record_str(self, gametape_id):
        """Helper to get W/L record string"""
        rec = self.game_state['gametape_records'].get(gametape_id, {'wins': 0, 'losses': 0})
        return f"[W:{rec['wins']} L:{rec['losses']}]"

def main():
    game = GameManager()
    while True:
        wins = game.game_state['total_wins']
        unlock_msg = f" (5v5 unlocks at {config.GAMES_TO_UNLOCK_5V5})" if wins < config.GAMES_TO_UNLOCK_5V5 else " (5v5 Unlocked!)"
        
        print(f"\nNBA STAT ATTACK | Tokens: {game.game_state['tokens']} | Total Wins: {wins}{unlock_msg}")
        print("1. Battle\n2. Shop\n3. Roster\n4. Quit")
        choice = config.get_valid_input("Choice: ", 4)
        if choice == 1: game.battle_menu()
        elif choice == 2: game.shop_menu()
        elif choice == 3: game.view_roster()
        elif choice == 4: break

if __name__ == "__main__":
    main()