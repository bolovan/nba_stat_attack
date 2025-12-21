"""
NBA Data Manager (Offline Database Version)
Replaces API calls with local SQLite queries for instant performance.
"""

import sqlite3
import json
import random
import game_config as config

DB_FILE = 'nba_stats.db'

class NBADataManager:
    def __init__(self):
        # Connect to local database
        # check_same_thread=False allows simple usage across game loops
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Access columns by name
        self.cache = {} # Keep memory cache for super-speed

    def get_all_players(self):
        """Get all players present in the database (Legacy support)"""
        # This returns unique people, regardless of season
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT DISTINCT p.id, p.full_name
                FROM players p
                JOIN game_logs g ON p.id = g.player_id
                ORDER BY p.full_name
            """)
            rows = cursor.fetchall()
            
            players = []
            for r in rows:
                parts = r['full_name'].split(' ', 1)
                first = parts[0]
                last = parts[1] if len(parts) > 1 else ''
                
                players.append({
                    'id': r['id'],
                    'full_name': r['full_name'],
                    'first_name': first,
                    'last_name': last
                })
            return players
        except Exception as e:
            print(f"Database Error (get_all_players): {e}")
            return []

    def get_available_card_pool(self):
        """
        NEW: Returns a list of every valid (Player + Season) combination.
        This is used for the Shop and Starter selection to support multiple seasons.
        """
        try:
            cursor = self.conn.cursor()
            # Get every player-season combo that has enough games
            cursor.execute("""
                SELECT DISTINCT g.player_id, g.season_id, p.full_name
                FROM game_logs g
                JOIN players p ON g.player_id = p.id
                ORDER BY p.full_name, g.season_id DESC
            """)
            rows = cursor.fetchall()
            
            pool = []
            for r in rows:
                pool.append({
                    'id': r['player_id'],
                    'season': r['season_id'],
                    'full_name': r['full_name']
                })
            return pool
        except Exception as e:
            print(f"Database Error (get_available_card_pool): {e}")
            return []

    def get_player_season_stats(self, player_id, season='2024-25'):
        """Calculate season averages from local game logs"""
        cache_key = f"stats_{player_id}_{season}"
        if cache_key in self.cache: return self.cache[cache_key]

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 
                    count(*) as GP,
                    AVG(min) as MIN,
                    AVG(pts) as PTS,
                    AVG(ast) as AST,
                    AVG(tov) as TOV,
                    AVG(reb) as REB,
                    AVG(stl) as STL,
                    AVG(blk) as BLK,
                    AVG(fgm) as FGM,
                    AVG(fga) as FGA,
                    AVG(fg3m) as FG3M,
                    AVG(fg3a) as FG3A,
                    AVG(ftm) as FTM,
                    AVG(fta) as FTA
                FROM game_logs
                WHERE player_id = ? AND season_id = ?
            """, (player_id, season))
            
            row = cursor.fetchone()
            
            if not row or row['GP'] == 0:
                return None
            
            stats = dict(row)
            stats['player_id'] = player_id
            stats['season'] = season
            stats['games_played'] = stats['GP']
            
            if stats['MIN'] < config.MIN_AVERAGE_MPG:
                return None
                
            self.cache[cache_key] = stats
            return stats
            
        except Exception as e:
            print(f"Database Error (get_player_season_stats): {e}")
            return None

    def get_player_games(self, player_id, season='2024-25'):
        """Get all games for a player from local DB"""
        cache_key = f"games_{player_id}_{season}"
        if cache_key in self.cache: return self.cache[cache_key]

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM game_logs 
                WHERE player_id = ? AND season_id = ?
                ORDER BY game_date DESC
            """, (player_id, season))
            
            rows = cursor.fetchall()
            games = []
            
            for r in rows:
                if r['min'] < config.MIN_MINUTES_PLAYED:
                    continue
                    
                game_data = dict(r)
                # FIX: Map 'game_date' to 'date' to prevent KeyError in game_manager
                if 'game_date' in game_data:
                    game_data['date'] = game_data['game_date']
                
                games.append(game_data)
                
            self.cache[cache_key] = games
            return games
            
        except Exception as e:
            print(f"Database Error (get_player_games): {e}")
            return []

    def get_game_moves(self, player_id, game_id, calculate_labels=False):
        """Generate moves and labels from local data"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM game_logs WHERE player_id=? AND game_id=?", (player_id, game_id))
        row = cursor.fetchone()
        
        if not row:
            return self.get_fallback_moves()
            
        game_stats = dict(row)
        # FIX: Map 'game_date' to 'date'
        if 'game_date' in game_stats:
            game_stats['date'] = game_stats['game_date']
        
        moves = self.generate_moves_from_game_stats(game_stats)
        
        labels = []
        if calculate_labels:
            labels = self.detect_gametape_labels_offline(player_id, game_id, game_stats)
            moves = self.apply_label_bonuses(moves, labels)
            
        plus_minus = game_stats.get('plus_minus', 0)
        
        return {
            'moves': moves,
            'labels': labels,
            'plus_minus': plus_minus
        }

    def detect_gametape_labels_offline(self, player_id, game_id, game_stats):
        """Query box_scores table for advanced JSON data"""
        labels = []
        label_scores = {}
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT data_json FROM box_scores WHERE game_id=?", (game_id,))
        row = cursor.fetchone()
        
        advanced_stats = {}
        hustle_stats = {}
        usage_stats = {}
        scoring_stats = {}
        
        if row:
            try:
                full_data = json.loads(row['data_json'])
                def find_player(dataset):
                    for p in dataset:
                        # Handle string/int mismatches on ID
                        if str(p.get('PLAYER_ID')) == str(player_id) or str(p.get('personId')) == str(player_id):
                            return p
                    return {}

                advanced_stats = find_player(full_data.get('advanced', []))
                hustle_stats = find_player(full_data.get('hustle', []))
                usage_stats = find_player(full_data.get('usage', []))
                scoring_stats = find_player(full_data.get('scoring', []))
            except:
                pass 

        # --- LOGIC ---
        pts, reb, ast = game_stats['pts'], game_stats['reb'], game_stats['ast']
        stl, blk = game_stats['stl'], game_stats['blk']
        doubles = sum([1 for x in [pts, reb, ast, stl, blk] if x >= 10])
        if doubles >= 3: label_scores['Triple Double'] = 1
        
        usg_pct = usage_stats.get('USG_PCT', 0.2)
        if usg_pct < 1: usg_pct *= 100
        
        if game_stats['min'] <= 24 and pts >= 15:
            fg_pct = game_stats['fgm'] / game_stats['fga'] if game_stats['fga'] > 0 else 0
            if fg_pct > 0.48: label_scores['Microwave'] = 2
            
        deflections = hustle_stats.get('DEFLECTIONS', 0)
        charges = hustle_stats.get('CHARGES_DRAWN', 0)
        if deflections == 0 and charges == 0:
            if stl >= 2 and game_stats['pf'] >= 4: label_scores['Stopper'] = 3
        elif deflections >= 2 and charges >= 1:
            label_scores['Stopper'] = 3
            
        screen_assists = hustle_stats.get('SCREEN_ASSISTS', 0)
        if screen_assists == 0:
            if game_stats['oreb'] >= 3 and game_stats['pf'] >= 4: label_scores['Bruiser'] = 4
        elif screen_assists >= 4:
            label_scores['Bruiser'] = 4
            
        if game_stats['plus_minus'] > 10 and ast >= 3 and pts <= 15:
            label_scores['Glue Guy'] = 5
            
        ast_to = advanced_stats.get('AST_TO', 0.0)
        if ast_to == 0 and game_stats['tov'] > 0: ast_to = ast / game_stats['tov']
        if ast >= 6 and ast_to > 3.0:
            label_scores['Floor General'] = 6
            
        if blk >= 2 and game_stats['dreb'] >= 8:
            label_scores['Rim Protector'] = 7
            
        fta, fga = game_stats['fta'], game_stats['fga']
        if fga > 0 and fta >= 6 and game_stats['fg3a'] <= 3 and (fta/fga) > 0.35:
            label_scores['Slasher'] = 8
            
        pct_ast_3pm = scoring_stats.get('PCT_AST_3PM', 0.0)
        if game_stats['fg3m'] >= 2 and pct_ast_3pm > 0.75 and usg_pct < 18:
            label_scores['3 and D'] = 9
            
        sorted_labels = sorted(label_scores.items(), key=lambda x: x[1])
        return [label for label, _ in sorted_labels[:2]]

    def generate_moves_from_game_stats(self, game_stats):
        moves = []
        
        # Attacks
        fgm_2pt = game_stats['fgm'] - game_stats['fg3m']
        for _ in range(max(0, fgm_2pt)): moves.append({'type': 'attack', 'description': 'Made 2PT'})
        for _ in range(game_stats['fg3m']): moves.append({'type': 'strong_attack', 'description': 'Made 3PT'})
        for _ in range(game_stats['ftm']): moves.append({'type': 'weak_attack', 'description': 'Made FT'})
        
        # Misses
        misses = (game_stats['fga'] - game_stats['fgm']) + (game_stats['fta'] - game_stats['ftm'])
        for _ in range(misses): moves.append({'type': 'miss', 'description': 'Missed Shot'})
        
        # Others
        for _ in range(game_stats['dreb']): moves.append({'type': 'defensive_rebound', 'description': 'D-Reb'})
        for _ in range(game_stats['oreb']): moves.append({'type': 'offensive_rebound', 'description': 'O-Reb'})
        for _ in range(game_stats['ast']): moves.append({'type': 'assist', 'description': 'Assist'})
        for _ in range(game_stats['stl']): moves.append({'type': 'steal', 'description': 'Steal'})
        for _ in range(game_stats['blk']): moves.append({'type': 'block', 'description': 'Block'})
        for _ in range(game_stats['tov']): moves.append({'type': 'turnover', 'description': 'Turnover'})
        for _ in range(game_stats['pf']): moves.append({'type': 'foul', 'description': 'Foul'})
        
        random.shuffle(moves)
        return moves

    def apply_label_bonuses(self, moves, labels):
        modified = moves.copy()
        for label in labels:
            if label == '3 and D':
                rem_count = 0
                new_moves = []
                for m in modified:
                    if m['type'] == 'miss' and rem_count < 2:
                        rem_count += 1
                    else:
                        new_moves.append(m)
                modified = new_moves
            elif label == 'Glue Guy':
                for _ in range(4): modified.append({'type': 'weak_attack', 'description': 'Bonus FT'})
        random.shuffle(modified)
        return modified

    def get_fallback_moves(self):
        return {'moves': [], 'labels': [], 'plus_minus': 0}

    def validate_gametape(self, moves_data, game_stats):
        moves = moves_data.get('moves', [])
        if len([m for m in moves if m['type'] != 'miss']) < config.MIN_MOVES_REQUIRED:
            return False, "Not enough moves"
        if not any(m['type'] in ['attack', 'strong_attack', 'weak_attack'] for m in moves):
            return False, "No attacks"
        return True, "Valid"