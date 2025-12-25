import streamlit as st
from game_manager import GameManager
import game_config as config
import battle_engine  
import random
import time
import math
from PIL import Image
import requests
from io import BytesIO
import json
import os

# 1. Page Configuration
st.set_page_config(
    page_title="NBA Stat Attack",
    page_icon="🏀",
    layout="wide"
)

# 2. Initialize Game Engine & Session State
if 'game_manager' not in st.session_state:
    with st.spinner("Initializing Game Engine..."):
        try:
            st.session_state['game_manager'] = GameManager()
            st.success("Game Engine Initialized!")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Failed to initialize game: {e}")
            st.stop()

# Helper accessors
gm = st.session_state['game_manager']
state = gm.game_state

# Initialize Battle State if not present
if 'active_battle' not in st.session_state:
    st.session_state['active_battle'] = None 
if 'battle_mode' not in st.session_state:
    st.session_state['battle_mode'] = None 
if 'battle_setup_complete' not in st.session_state:
    st.session_state['battle_setup_complete'] = False

# Initialize 5v5 Roster Selection State
if 'roster_5v5_selections' not in st.session_state:
    st.session_state['roster_5v5_selections'] = []  # List of (card_id, tape_id) tuples
if 'current_player_selection' not in st.session_state:
    st.session_state['current_player_selection'] = None
if 'current_tape_selection' not in st.session_state:
    st.session_state['current_tape_selection'] = None

# --- HELPER FUNCTIONS FOR UI ---

@st.cache_data(show_spinner=False)
def get_pixelated_headshot(player_id, pixel_size=64, reduce_colors=False):
    """
    Downloads player headshot and creates a retro pixel art effect.
    """
    try:
        url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"
        response = requests.get(url)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            
            # Convert to RGBA immediately to avoid palette warnings
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Crop to focus on the face (NBA headshots have consistent framing)
            width, height = img.size
            left = width * 0.2
            right = width * 0.8
            top = height * 0.05
            bottom = height * 0.75
            img = img.crop((int(left), int(top), int(right), int(bottom)))
            
            # Convert RGBA to RGB with black background
            background = Image.new('RGB', img.size, (0, 0, 0))
            background.paste(img, mask=img.split()[3])
            img = background
            
            # Downscale with high-quality resampling
            small = img.resize((pixel_size, pixel_size), resample=Image.LANCZOS)
            
            # Reduce color palette for 8-bit aesthetic
            if reduce_colors:
                small = small.quantize(colors=64, dither=Image.Dither.NONE).convert('RGB')
            
            # Upscale with NEAREST for crisp pixels
            result = small.resize((128, 128), resample=Image.NEAREST)
            
            return result
        return None
    except Exception as e:
        print(f"Error processing headshot: {e}")
        return None

def render_health_bar(current, max_hp, label="HP"):
    pct = max(0.0, min(1.0, current / max_hp))
    st.write(f"**{label}**: {math.ceil(current)}/{math.ceil(max_hp)}")
    st.progress(pct)

def get_player_id_from_card(card_id):
    pid, _ = gm.parse_card_id(card_id)
    return pid

# 3. Sidebar Navigation
with st.sidebar:
    st.title("🏀 NBA Stat Attack")
    st.markdown(f"**Tokens:** {state.get('tokens', 0)}")
    
    wins = state.get('total_wins', 0)
    st.markdown(f"**Wins to unlock 5v5:** {wins} / {config.GAMES_TO_UNLOCK_5V5}")
    if wins < config.GAMES_TO_UNLOCK_5V5:
        st.progress(wins / config.GAMES_TO_UNLOCK_5V5)
    else:
        st.success("5v5 Unlocked!")
        
    st.divider()
    
    def nav_to(page):
        st.session_state['menu_choice'] = page
        if page != 'battle':
            st.session_state['active_battle'] = None
            st.session_state['battle_setup_complete'] = False
            st.session_state['roster_5v5_selections'] = []
            
    if st.button("🏠 Main Menu", use_container_width=True): nav_to('main')
    if st.button("⚔️ Battle Arena", use_container_width=True): nav_to('battle')
    if st.button("🛒 Shop", use_container_width=True): nav_to('shop')
    if st.button("📋 Roster", use_container_width=True): nav_to('roster')
    if st.button("💾 Save / Settings", use_container_width=True): nav_to('settings')
    if st.button("❓ FAQ / Guide", use_container_width=True): nav_to('faq')

if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = 'main'

choice = st.session_state['menu_choice']

# --- MAIN PAGES ---

if choice == 'main':
    st.header("Welcome to the Court")
    

    col1, col2 = st.columns([1, 2])
    
    with col1:
        player_cards = state.get('player_cards', [])
        img = None
        if player_cards:
            pid = get_player_id_from_card(player_cards[0])
            if pid:
                img = get_pixelated_headshot(pid, pixel_size=64)
        
        if img:
            st.image(img, caption="Your Player", width=250)
        else:
            st.image("https://cdn.nba.com/headshots/nba/latest/1040x760/2544.png", width=250)

    with col2:
        st.write("### Welcome to version 2.2.0")
        st.info("Use the sidebar on the left to navigate. Upper left arrow on mobile.")
        st.info("Save game in sidebar to not lose progress.")
        st.markdown(f"""
        **Status:**
        * **Tokens:** {state.get('tokens', 0)}
        * **Players Owned:** {len(player_cards)}/{config.MAX_ROSTER_SIZE}
        * **Total Wins:** {state.get('total_wins', 0)}
        """)

elif choice == 'settings':
    st.header("💾 Data Management")
    st.info("Manage your save file. Download it to backup your progress or upload a file to restore it.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Download Save")
        # Convert state to JSON string
        save_json = json.dumps(state, indent=2)
        st.download_button(
            label="⬇️ Download Save File",
            data=save_json,
            file_name="nba_stat_attack_save.json",
            mime="application/json"
        )
        st.success("Click to save your progress to your device.")

    with col2:
        st.subheader("Upload Save")
        uploaded_file = st.file_uploader("Upload a .json save file", type=['json'])
        
        if uploaded_file is not None:
            if st.button("Load Uploaded Save"):
                try:
                    # Read file
                    content = json.load(uploaded_file)
                    
                    # Basic validation
                    if 'tokens' in content and 'player_cards' in content:
                        # Update Game State
                        gm.game_state.update(content)
                        gm.save_game() # Save to local disk
                        st.success("Save file loaded successfully!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Invalid save file format.")
                except Exception as e:
                    st.error(f"Error loading file: {e}")
        
    st.divider()
    with st.expander("Danger Zone"):
        st.warning("This will reset your current game progress. You can restore it by uploading a previously downloaded save file.")
        if st.button("🗑️ Reset Session (New Game)", type="primary"):
            # Clear all game-related session state
            if 'saved_game_data' in st.session_state:
                del st.session_state['saved_game_data']
            if 'game_manager' in st.session_state:
                del st.session_state['game_manager']
                
            st.warning("Game reset! Restarting...")
            time.sleep(1)
            st.rerun()


elif choice == 'faq':
    st.header("❓ Game Guide & FAQ")
    
    with st.expander("📖 READ THE MANUAL (How to Play)", expanded=True):
        st.markdown("""
        ### 🎮 Core Concepts
        * **Players:** Fighters with base stats from their season averages, based on players from season 2016-2017 to 2024-2025
        * **Gametapes:** Equipment that modifies stats based on a specific real-life game.
        * **Labels:** Special bonuses earned from historic performances (e.g., Triple Double).

        ### ⚔️ Battle System (1v1)
        * Turn based battle between you and randomized opponent
        * **Action Deck:** Your moves are generated from the box score. (e.g., 20 FGA = 20 Attack Cards).
            * **Field Goals:** FGM are attacks. FTM are weak attacks. 3PM are strong attacks. Missed shots are missed attacks.
            * **Defensive Rebounds:** Defensive Buff for your player.
            * **Assists:** Attack Buff for your player.
            * **Offensive Rebounds:** Self-Heal for your player.
            * **Steals:** Attack Debuff for your opponent.
            * **Blocks:** Defensive Debuff For your opponent.
            * **Turnovers:** Skips Turn.
            * **Fouls:** Self-Damage
        * **Strategy:** Use **Timeouts** to refresh cards if you run out of moves. Action cards will refill smaller portion.
        * **Mistakes:** Offensive moves can trigger Turnovers. Defensive moves can trigger Fouls.

        ### 🏀 Coach Mode (5v5)
        * Simulated battle based on offensive and defensive strategies against random opponents.
        * Team selected from top 5 players in roster order
        * Select offensive and defensive strategies for each quarter.
            * **Offensive Strategies**
                * **Feed the Hot Hand:** Prioritize attacks from strongest attacker and assists from teammates.
                * **Ball Movement:** String together multiple assists before attacking.
                * **Crash the Glass:** Prioritize Offensive Rebounds to Heal. Good for second and third quarter if overall HP low.
                * **Seven Seconds or Less:** Attack, attack, attack, no buffing.
            * **Defensive Strategies**
                * **Lockdown Paint:** Prioritizes Block cards.
                * **Full Court Press:** Prioritizes Steal cards.
                * **Box Out:** Prioritizes Defensive rebounds cards.
                * **Switch Everything:** Uses whatever defensive cards is most abundant.
            * **Synergy:** Assists buff teammates. O-Rebounds heal allies.
        * **Overtime:** If survivors are tied after Q4, a 1v1 Sudden Death duel determines the winner.

        ### 💰 Economy
        * **Tokens:** Earn by winning. Spend in the Shop.
        * **Game Tape Retirement:** * 16 Wins = **Hall of Fame** (Retired + Bonus Tokens)
            * 4 Losses = **G-League Relegation for Game Tape** (Cut from roster inventory)
        """)
        
    with st.expander("🏷️ Labels Glossary"):
        st.markdown("""
        * **Triple Double:** +15% Defense
        * **Microwave:** Double Damage on first hit
        * **Stopper:** Plus 2 'Miss' to opponents movelist
        * **Floor General:** Assists grant 2 Attack Buff Stacks
        * **Rim Protector:** Blocks debuff x2
        * **Bruiser:** +15 Max HP
        * **3 and D:** Removes 2 'Miss' from movelist
        * **Glue Guy:** Adds 4 extra Free Throws to movelist
        """)

elif choice == 'roster':
    st.header("Your Roster")
    if not state.get('player_cards'):
        st.warning("No players! Visit the Shop.")
    
    for i, card_id in enumerate(state.get('player_cards', [])):
        name = gm.get_player_name(card_id)
        pid = get_player_id_from_card(card_id)
        
        with st.expander(f"🏀 {name}", expanded=(i==0)):
            c1, c2 = st.columns([1, 3])
            with c1:
                img = get_pixelated_headshot(pid, pixel_size=64)
                if img: st.image(img)

                if i > 0:
                    if st.button("⬆️ Move to Top", key=f"move_top_{card_id}"):
                        state['player_cards'].remove(card_id)
                        state['player_cards'].insert(0, card_id)
                        gm.save_game()
                        st.rerun()
                
            with c2:
                rec = state['player_records'].get(card_id, {'wins':0, 'losses':0})
                st.write(f"**Record:** {rec['wins']}W - {rec['losses']}L")
                
                # Base Stats
                stats = gm.nba_manager.get_player_season_stats(pid, gm.parse_card_id(card_id)[1])
                if stats:
                    base = config.calculate_base_stats(stats)
                    st.caption(f"Base: HP {base['hp']:.0f} | ATK {base['attack']:.1f} | DEF {base['defense']:.1f}")

                st.divider()
                tapes = state['gametapes'].get(card_id, [])
                if tapes:
                    st.write("**Equipped Gametapes:**")
                    for tid in tapes:
                        t_name = gm.get_display_name(tid)
                        t_rec = gm.get_tape_record_str(tid)
                        
                        # --- ENHANCED GAMETAPE DETAILS ---
                        game_id = tid.split('_')[1]
                        moves_data = gm.nba_manager.get_game_moves(pid, game_id)
                        
                        st.markdown(f"**{t_name}** {t_rec}")
                        
                        # Calculate Stat Changes
                        game_stats = moves_data.get('game_stats', {}) # Need to ensure this is passed or fetch again
                        # For now, fetching game logic directly:
                        games = gm.nba_manager.get_player_games(pid) 
                        target_game = next((g for g in games if str(g['game_id']) == str(game_id)), None)
                        
                        if target_game and stats:
                            # Quick logic to show diffs (simplified)
                            # Ideally reuse create_gametape_display_name logic but break it out
                            # For UI simplicity, let's just list the moves
                            pass

                        # List Moves Breakdown
                        moves = moves_data.get('moves', [])
                        counts = {}
                        for m in moves:
                            counts[m['type']] = counts.get(m['type'], 0) + 1
                        
                        move_order = [
                            'attack', 'weak_attack', 'strong_attack', 'miss',
                            'defensive_rebound', 'offensive_rebound', 'assist',
                            'steal', 'block', 'turnover', 'foul'
                        ]

                        # Format as chips/text
                        move_str = " | ".join([f"{k.replace('_',' ').title()}: {counts[k]}" for k in move_order if k in counts])
                        st.caption(f"Moves: {move_str}")
                        st.markdown("---")
                else:
                    st.warning("No gametapes equipped.")

        # --- HALL OF FAME SECTION ---
    st.divider()
    st.header("🏆 Hall of Fame")
    
    hall_of_fame = state.get('hall_of_fame', [])
    
    if not hall_of_fame:
        st.info("No legends yet! Gametapes that reach 16 wins are immortalized here.")
    else:
        st.caption(f"🌟 {len(hall_of_fame)} Legendary Performance(s)")
        
        # Group tapes by player_id
        player_tapes = {}
        for tape_id in hall_of_fame:
            parts = tape_id.split('_')
            if len(parts) >= 2:
                player_id = parts[0]
                if player_id not in player_tapes:
                    player_tapes[player_id] = []
                player_tapes[player_id].append(tape_id)
        
        # Display grouped by player
        for player_id, tapes in player_tapes.items():
            # Get player name from database
            try:
                cursor = gm.nba_manager.conn.cursor()
                cursor.execute("SELECT full_name FROM players WHERE id=?", (int(player_id),))
                row = cursor.fetchone()
                player_name = row['full_name'] if row else f"Player {player_id}"
            except:
                player_name = f"Player {player_id}"
            
            # Display player entry
            hof_col1, hof_col2 = st.columns([1, 4])
            
            with hof_col1:
                img = get_pixelated_headshot(int(player_id), pixel_size=64)
                if img:
                    st.image(img, width=80)
                else:
                    st.markdown("🏀")
            
            with hof_col2:
                st.markdown(f"**{player_name}** ({len(tapes)} 🏆)")
                
                # List all tapes for this player
                for tape_id in tapes:
                    game_id = tape_id.split('_')[1]
                    tape_name = state.get('gametape_metadata', {}).get(tape_id, tape_id)
                    box_score_url = f"https://www.nba.com/game/{game_id}/box-score"
                    
                    st.caption(f"📼 {tape_name}")
                    st.markdown(f"[📊 Box Score]({box_score_url})", unsafe_allow_html=True)
            
            st.markdown("---")
            

elif choice == 'shop':
    st.header("🛒 The Shop")
    
    tab_buy, tab_sell = st.tabs(["Buy Items", "Sell Items"])
    
    with tab_buy:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"Buy Gametape ({config.GAMETAPE_COST} Tokens)")
            player_options = {cid: gm.get_player_name(cid) for cid in state.get('player_cards', [])}
            if player_options:
                sel_card = st.selectbox("Player:", options=list(player_options.keys()), format_func=lambda x: player_options[x])
                if st.button("Buy Tape"):
                    if state['tokens'] < config.GAMETAPE_COST:
                        st.error("Not enough tokens!")
                    else:
                        success, msg = gm.buy_gametape_logic(sel_card)
                        if success:
                            st.success(f"✅ Bought: {msg}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning(msg)
            else: st.warning("Buy a player first.")

        with c2:
            st.subheader(f"Buy Player ({config.PLAYER_CARD_COST} Tokens)")
            if st.button("Draft Player"):
                if state['tokens'] < config.PLAYER_CARD_COST: st.error("No tokens")
                else:
                    with st.spinner("Scouting..."):
                        pool = gm.nba_manager.get_available_card_pool()
                        found = False
                        for _ in range(50):
                            cand = random.choice(pool)
                            cid = f"{cand['id']}_{cand['season']}"
                            if cid in state['player_cards']: continue
                            stats = gm.nba_manager.get_player_season_stats(cand['id'], cand['season'])
                            if not stats: continue
                            
                            games = gm.nba_manager.get_player_games(cand['id'], cand['season'])
                            valid_tape = None
                            if games:
                                for g in random.sample(games, min(5, len(games))):
                                    m = gm.nba_manager.get_game_moves(cand['id'], g['game_id'], calculate_labels=True)
                                    if gm.nba_manager.validate_gametape(m, g)[0]:
                                        valid_tape = g; valid_labels = m.get('labels', []); break
                            
                            if valid_tape:
                                state['tokens'] -= config.PLAYER_CARD_COST
                                state['player_cards'].append(cid)
                                state['player_records'][cid] = {'wins':0, 'losses':0}
                                tid = f"{cand['id']}_{valid_tape['game_id']}"
                                state['gametapes'][cid] = [tid]
                                state['gametape_records'][tid] = {'wins':0, 'losses':0}
                                tname = gm.create_gametape_display_name(valid_tape, stats, valid_labels)
                                state['gametape_metadata'][tid] = tname
                                gm.save_game()
                                st.success(f"Drafted: {cand['full_name']} ({cand['season']})")
                                found = True
                                time.sleep(2)
                                st.rerun()
                                break
                        if not found: st.error("Scouting failed.")

    with tab_sell:
        sc1, sc2 = st.columns(2)
        
        with sc1:
            st.subheader(f"Sell Gametape (+{config.GAMETAPE_SELL_VALUE} Token)")
            all_tapes = []
            for cid, tapes in state['gametapes'].items():
                p_name = gm.get_player_name(cid)
                for tid in tapes:
                    t_name = gm.get_display_name(tid)
                    all_tapes.append( (tid, f"{p_name} | {t_name}", cid) )
            
            if not all_tapes:
                st.info("No gametapes to sell.")
            else:
                tape_opts = {t[0]: t[1] for t in all_tapes}
                sel_tape_id = st.selectbox("Select Tape to Sell:", options=list(tape_opts.keys()), format_func=lambda x: tape_opts[x], key="sell_tape_select")
                owner_id = next((t[2] for t in all_tapes if t[0] == sel_tape_id), None)

                if st.button("Confirm Sell Tape", key="btn_sell_tape"):
                    if owner_id and sel_tape_id:
                        state['gametapes'][owner_id].remove(sel_tape_id)
                        state['tokens'] += config.GAMETAPE_SELL_VALUE
                        gm.save_game()
                        st.success("Tape sold!")
                        time.sleep(1)
                        st.rerun()

        with sc2:
            st.subheader(f"Sell Player (+{config.PLAYER_CARD_SELL_VALUE} Tokens)")
            if len(state['player_cards']) <= 1:
                st.warning("Must keep at least 1 player.")
            else:
                p_opts_sell = {cid: gm.get_player_name(cid) for cid in state['player_cards']}
                sel_p_sell = st.selectbox("Select Player to Sell:", options=list(p_opts_sell.keys()), format_func=lambda x: p_opts_sell[x], key="sell_player_select")
                
                if st.button("Confirm Release Player", key="btn_sell_player"):
                    tape_count = len(state['gametapes'].get(sel_p_sell, []))
                    total_val = config.PLAYER_CARD_SELL_VALUE + (tape_count * config.GAMETAPE_SELL_VALUE)
                    state['player_cards'].remove(sel_p_sell)
                    if sel_p_sell in state['gametapes']:
                        del state['gametapes'][sel_p_sell]
                    state['tokens'] += total_val
                    gm.save_game()
                    st.success(f"Player released for {total_val} tokens.")
                    time.sleep(1)
                    st.rerun()

elif choice == 'battle':
    st.header("⚔️ Battle Arena")
    
    if st.session_state['active_battle'] is None:
        tab1, tab2 = st.tabs(["1v1 Duel", "5v5 Team Battle"])
        
        with tab1:
            st.subheader("Quick Battle Setup")
            p_opts = {cid: gm.get_player_name(cid) for cid in state.get('player_cards', [])}
            
            if not p_opts:
                st.warning("No players available.")
            else:
                c1, c2 = st.columns([1, 2])
                with c1:
                    sel_p = st.selectbox("Select Fighter", list(p_opts.keys()), format_func=lambda x: p_opts[x])
                    pid = get_player_id_from_card(sel_p)
                    img = get_pixelated_headshot(pid, pixel_size=64)
                    if img: st.image(img)
                
                with c2:
                    tapes = state['gametapes'].get(sel_p, [])
                    if tapes:
                        t_opts = {tid: f"{gm.get_display_name(tid)} {gm.get_tape_record_str(tid)}" for tid in tapes}
                        sel_t = st.selectbox("Select Gametape", list(t_opts.keys()), format_func=lambda x: t_opts[x])
                        
                        if st.button("START DUEL"):
                            p_unit = gm.create_battle_unit(sel_p, sel_t, calculate_labels=True)
                            o_unit = gm.generate_random_opponent()
                            
                            if p_unit and o_unit:
                                st.session_state['battle_tracking'] = {'type': '1v1', 'pid': sel_p, 'tid': sel_t}
                                st.session_state['active_battle'] = battle_engine.Battle(p_unit, o_unit)
                                st.session_state['battle_mode'] = '1v1'
                                st.rerun()
                            else:
                                st.error("Error creating battle units.")
                    else:
                        st.warning("No gametapes for this player.")

        with tab2:
            st.subheader("🏀 Coach Mode - Build Your Roster")
            wins = state.get('total_wins', 0)
            valid_players = [cid for cid in state['player_cards'] if state['gametapes'].get(cid)]
            valid_count = len(valid_players)
            
            if wins < config.GAMES_TO_UNLOCK_5V5 or valid_count < 5:
                st.error(f"🔒 Locked! Need {config.GAMES_TO_UNLOCK_5V5} wins and 5 players with gametapes.")
                st.info(f"Current: {wins} wins, {valid_count} valid players")
            else:
                # --- ROSTER SELECTION UI ---
                st.info("Select 5 players and their gametapes for your starting lineup.")
                
                # Get already selected player IDs to prevent duplicates
                selected_player_ids = [sel[0] for sel in st.session_state['roster_5v5_selections']]
                
                # Filter available players (exclude already selected)
                available_players = [cid for cid in valid_players if cid not in selected_player_ids]
                
                # Show current roster
                if st.session_state['roster_5v5_selections']:
                    st.markdown("### 📋 Current Lineup")
                    for i, (cid, tid) in enumerate(st.session_state['roster_5v5_selections']):
                        col_name, col_tape, col_remove = st.columns([2, 3, 1])
                        with col_name:
                            st.write(f"**{i+1}.** {gm.get_player_name(cid)}")
                        with col_tape:
                            st.caption(f"📼 {gm.get_display_name(tid)}")
                        with col_remove:
                            if st.button("❌", key=f"remove_{i}"):
                                st.session_state['roster_5v5_selections'].pop(i)
                                st.rerun()
                    st.divider()
                
                # Selection dropdowns (only show if roster not full)
                if len(st.session_state['roster_5v5_selections']) < 5:
                    st.markdown(f"### Add Player ({len(st.session_state['roster_5v5_selections'])}/5)")
                    
                    sel_col1, sel_col2 = st.columns(2)
                    
                    with sel_col1:
                        st.markdown("**Select Player**")
                        if not available_players:
                            st.warning("No more players available!")
                            selected_player = None
                        else:
                            player_options = {cid: gm.get_player_name(cid) for cid in available_players}
                            selected_player = st.selectbox(
                                "Player:",
                                options=list(player_options.keys()),
                                format_func=lambda x: player_options[x],
                                key="5v5_player_select",
                                label_visibility="collapsed"
                            )
                    
                    with sel_col2:
                        st.markdown("**Select Gametape**")
                        if selected_player:
                            tapes = state['gametapes'].get(selected_player, [])
                            if tapes:
                                tape_options = {
                                    tid: f"{gm.get_display_name(tid)} {gm.get_tape_record_str(tid)}" 
                                    for tid in tapes
                                }
                                selected_tape = st.selectbox(
                                    "Gametape:",
                                    options=list(tape_options.keys()),
                                    format_func=lambda x: tape_options[x],
                                    key="5v5_tape_select",
                                    label_visibility="collapsed"
                                )
                            else:
                                st.warning("No gametapes!")
                                selected_tape = None
                        else:
                            st.info("← Select a player first")
                            selected_tape = None
                    
                    # Add to roster button
                    if selected_player and selected_tape:
                        if st.button("➕ Add to Lineup", type="secondary", use_container_width=True):
                            st.session_state['roster_5v5_selections'].append((selected_player, selected_tape))
                            st.rerun()
                
                # Action buttons
                st.divider()
                btn_col1, btn_col2 = st.columns(2)
                
                with btn_col1:
                    if st.button("🗑️ Clear Roster", use_container_width=True):
                        st.session_state['roster_5v5_selections'] = []
                        st.rerun()
                
                with btn_col2:
                    roster_ready = len(st.session_state['roster_5v5_selections']) == 5
                    if st.button(
                        "🏀 START SEASON GAME", 
                        type="primary", 
                        disabled=not roster_ready,
                        use_container_width=True
                    ):
                        # Build team from selections
                        team_units = []
                        track_info = []
                        
                        for cid, tid in st.session_state['roster_5v5_selections']:
                            unit = gm.create_battle_unit(cid, tid)
                            if unit:
                                team_units.append(unit)
                                track_info.append((cid, tid))
                        
                        # Generate opponent team
                        opp_units = [gm.generate_random_opponent() for _ in range(5)]
                        opp_units = [u for u in opp_units if u]
                        
                        if len(team_units) == 5 and len(opp_units) == 5:
                            st.session_state['battle_tracking'] = {'type': '5v5', 'roster': track_info}
                            st.session_state['active_battle'] = battle_engine.Battle5v5(team_units, opp_units)
                            st.session_state['battle_mode'] = '5v5'
                            # Clear roster selections for next game
                            st.session_state['roster_5v5_selections'] = []
                            st.rerun()
                        else:
                            st.error("Error creating teams. Please try again.")
                
                if not roster_ready:
                    st.caption(f"⚠️ Select {5 - len(st.session_state['roster_5v5_selections'])} more player(s) to start")
    else:
        battle = st.session_state['active_battle']
        mode = st.session_state['battle_mode']
        
        # 1v1 INTERFACE
        if mode == '1v1':
            p = battle.player
            o = battle.opponent
            
            # --- BATTLE HEADER WITH IMAGES ---
            c1, c2, c3 = st.columns([2, 1, 2])
            with c1:
                st.info(f"YOU: {p.name}")
                # Get Player Image
                p_img = get_pixelated_headshot(p.player_id, pixel_size=64)
                if p_img: st.image(p_img, width=150)
                
                render_health_bar(p.current_hp, p.max_hp)
                st.caption(f"⚔️ ATK: {p.attack:.0f} | 🛡️ DEF: {p.defense:.0f} | ⭐ PWR: {p.power_rating}")

                if p.labels:
                    st.caption(f"🏷️ {', '.join(p.labels)}")

                if p.attack_buff_stacks != 0:
                    buff_color = "🔥" if p.attack_buff_stacks > 0 else "🔻"
                    st.caption(f"{buff_color} Atk Buff: {p.attack_buff_stacks:+d}")
                if p.defense_buff_stacks != 0:
                    buff_color = "🛡️" if p.defense_buff_stacks > 0 else "🔻"
                    st.caption(f"{buff_color} Def Buff: {p.defense_buff_stacks:+d}")
                
            with c2:
                st.markdown(f"<h1 style='text-align: center;'>VS</h1>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center;'>Turn {battle.turn_count}</p>", unsafe_allow_html=True)
                
            with c3:
                st.error(f"OPP: {o.name}")
                # Get Opponent Image
                o_img = get_pixelated_headshot(o.player_id, pixel_size=64)
                if o_img: st.image(o_img, width=150)
                
                render_health_bar(o.current_hp, o.max_hp)
                st.caption(f"⚔️ ATK: {o.attack:.0f} | 🛡️ DEF: {o.defense:.0f} | ⭐ PWR: {o.power_rating}")
                
                tape_name = gm.create_gametape_display_name(o.gametape['game_stats'], o.season_stats, o.labels)
                st.caption(f"📼 Tape: {tape_name}")
                
                # Show labels if any
                if o.labels:
                    st.caption(f"🏷️ {', '.join(o.labels)}")
                
                # Show buffs (including negative)
                if o.attack_buff_stacks != 0:
                    buff_color = "🔥" if o.attack_buff_stacks > 0 else "🔻"
                    st.caption(f"{buff_color} Atk Buff: {o.attack_buff_stacks:+d}")
                if o.defense_buff_stacks != 0:
                    buff_color = "🛡️" if o.defense_buff_stacks > 0 else "🔻"
                    st.caption(f"{buff_color} Def Buff: {o.defense_buff_stacks:+d}")

            st.divider()
            
            # Game Over Check
            if not p.is_alive() or not o.is_alive():
                winner = p if p.is_alive() else o
                if winner == p:
                    st.success("🏆 VICTORY!")
                    if 'reward_claimed' not in st.session_state:
                        track = st.session_state['battle_tracking']
                        # Check if this is OT from 5v5 or regular 1v1    
                        if track['type'] == '5v5':
                            # 5v5 overtime win - use 5v5 rewards
                            state['tokens'] += config.TOKENS_WIN_5V5
                            state['total_wins'] += 1
                            for cid, tid in track['roster']:
                                state['player_records'][cid]['wins'] += 1
                                state['gametape_records'][tid]['wins'] += 1
                                gm.check_retirement(tid, cid)
                        else:
                            # regular 1v1 win
                            state['tokens'] += config.TOKENS_WIN_1V1
                            state['total_wins'] += 1
                            state['player_records'][track['pid']]['wins'] += 1
                            state['gametape_records'][track['tid']]['wins'] += 1
                            gm.check_retirement(track['tid'], track['pid'])
                        gm.save_game()
                        st.session_state['reward_claimed'] = True
                else:
                    st.error("💀 DEFEAT")
                    if 'reward_claimed' not in st.session_state:
                        track = st.session_state['battle_tracking']

                        # check if this is OT from 5v5 or regular 1v1
                        if track['type'] == '5v5':
                            # 5v5 overtime loss - use 5v5 rewards
                            state['tokens'] += config.TOKENS_LOSE_5V5
                            for cid, tid in track['roster']:
                                state['player_records'][cid]['losses'] += 1
                                state['gametape_records'][tid]['losses'] += 1
                                gm.check_retirement(tid, cid)
                        else:
                            #regular 1v1 loss
                            state['tokens'] += config.TOKENS_LOSE_1V1
                            state['player_records'][track['pid']]['losses'] += 1
                            state['gametape_records'][track['tid']]['losses'] += 1
                            gm.check_retirement(track['tid'], track['pid'])
                        gm.save_game()
                        st.session_state['reward_claimed'] = True
                
                if st.button("Return to Arena"):
                    st.session_state['active_battle'] = None
                    if 'reward_claimed' in st.session_state: del st.session_state['reward_claimed']
                    st.rerun()
            
            else:
                # Battle Loop UI
                b_col1, b_col2 = st.columns([1, 1])
                
                with b_col1:
                    st.subheader("Action Deck")
                    row1 = st.columns(3)
                    row2 = st.columns(3)
                    
                    def perform_action(action_key):
                        p.action_deck[action_key] -= 1
                        battle.resolve_action(p, o, action_key)
                        if o.is_alive():
                           #check if opponent deck is empty and refill
                            if o.deck_is_empty():
                                o.refill_deck(0.5)
                            avail = [k for k, v in o.action_deck.items() if v > 0]
                            if avail:
                                ai_act = random.choice(avail)
                                o.action_deck[ai_act] -= 1
                                battle.resolve_action(o, p, ai_act)
                        st.rerun()

                    actions = [('attack', 'Attack'), ('defensive_rebound', 'D-Reb'), ('offensive_rebound', 'O-Reb'),
                               ('assist', 'Assist'), ('steal', 'Steal'), ('block', 'Block')]
                    
                    for i, (key, label) in enumerate(actions):
                        count = p.action_deck[key]
                        btn_col = row1 if i < 3 else row2
                        if btn_col[i%3].button(f"{label} ({count})", disabled=(count==0), use_container_width=True):
                            perform_action(key)
                    
                    if p.deck_is_empty():
                        st.warning("Deck Empty! Actions reset.")
                        p.refill_deck(0.25)
                        st.rerun()
                        
                    if st.button(f"Timeout ({p.timeouts_remaining})"):
                        if p.timeouts_remaining > 0:
                            battle.execute_timeout(p)
                            st.rerun()

                with b_col2:
                    st.subheader("Battle Log")
                    for log in reversed(battle.battle_log[-8:]):
                        st.text(f"> {log}")

        # 5v5 INTERFACE
        elif mode == '5v5':
            st.subheader(f"Q{battle.quarter} - Team Battle")
            
            tc1, tc2 = st.columns(2)
            with tc1: 
                st.info("YOUR TEAM")
                for u in battle.team1:
                    if u.is_alive():
                        render_health_bar(u.current_hp, u.max_hp, u.name)
                        # Show buffs and labels inline
                        status_parts = []
                        if u.attack_buff_stacks != 0:
                            status_parts.append(f"ATK:{u.attack_buff_stacks:+d}")
                        if u.defense_buff_stacks != 0:
                            status_parts.append(f"DEF:{u.defense_buff_stacks:+d}")
                        if u.labels:
                            status_parts.append(f"[{', '.join(u.labels)}]")
                        if status_parts:
                            st.caption(" | ".join(status_parts))
                    else:
                        st.markdown(f"~~{u.name}~~ 💀 **KO**")
            with tc2:
                st.error("OPPONENT")
                for u in battle.team2:
                    if u.is_alive():
                        render_health_bar(u.current_hp, u.max_hp, u.name)
                        # Show buffs inline
                        status_parts = []
                        if u.attack_buff_stacks != 0:
                            status_parts.append(f"ATK:{u.attack_buff_stacks:+d}")
                        if u.defense_buff_stacks != 0:
                            status_parts.append(f"DEF:{u.defense_buff_stacks:+d}")
                        if u.labels:
                            status_parts.append(f"[{', '.join(u.labels)}]")
                        if status_parts:
                            st.caption(" | ".join(status_parts))
                    else:
                        st.markdown(f"~~{u.name}~~ 💀 **KO**")
            
            if not battle.team_alive(battle.team1) or not battle.team_alive(battle.team2) or battle.quarter > 4:
                t1_alive = sum(1 for u in battle.team1 if u.is_alive())
                t2_alive = sum(1 for u in battle.team2 if u.is_alive())
                
                # Check Overtime Condition (Equal Survivors)
                if t1_alive > 0 and t2_alive > 0 and t1_alive == t2_alive:
                    st.warning("⚡ OVERTIME! Sudden Death!")
                    if st.button("BEGIN OVERTIME DUEL"):
                        # Get Champions (first living players)
                        p1 = next((u for u in battle.team1 if u.is_alive()), None)
                        p2 = next((u for u in battle.team2 if u.is_alive()), None)
                        
                        if p1 and p2:
                            # Switch to 1v1 Mode but keep 5v5 tracking data
                            # We create a new 1v1 battle using the EXISTING units (preserving HP/Deck)
                            st.session_state['active_battle'] = battle_engine.Battle(p1, p2)
                            st.session_state['battle_mode'] = '1v1' 
                            # We keep 'battle_tracking' as 5v5 so rewards process correctly for the whole team
                            st.rerun()
                        else:
                            st.error("Error finding OT champions.")
                # Winner determination
                else:
                    # Normal Win/Loss
                    user_won = t1_alive > t2_alive

                
                    if user_won:
                        st.success("🏆 TEAM VICTORY!")
                        if 'reward_claimed' not in st.session_state:
                            track = st.session_state['battle_tracking']
                            state['tokens'] += config.TOKENS_WIN_5V5
                            state['total_wins'] += 1
                            for cid, tid in track['roster']:
                                state['player_records'][cid]['wins'] += 1
                                state['gametape_records'][tid]['wins'] += 1
                                gm.check_retirement(tid, cid)
                            gm.save_game()
                            st.session_state['reward_claimed'] = True
                    else:
                        st.error("💀 TEAM DEFEAT")
                        if 'reward_claimed' not in st.session_state:
                            track = st.session_state['battle_tracking']
                            state['tokens'] += config.TOKENS_LOSE_5V5
                            for cid, tid in track['roster']:
                                state['player_records'][cid]['losses'] += 1
                                state['gametape_records'][tid]['losses'] += 1
                                gm.check_retirement(tid, cid)
                            gm.save_game()
                            st.session_state['reward_claimed'] = True
                            
                    if st.button("Return to Arena"):
                        st.session_state['active_battle'] = None
                        if 'reward_claimed' in st.session_state: del st.session_state['reward_claimed']
                        st.rerun()
            else:
                st.divider()
                st.subheader("Coach's Clipboard")
                
                if battle.quarter > 1:
                    st.caption(f"📋 Last Quarter Strategy: {battle.team1_strat['off']} / {battle.team1_strat['def']}")

                sc1, sc2, sc3 = st.columns(3)
                off_strat = sc1.selectbox("Offense", ["Feed the Hot Hand", "Ball Movement", "Crash the Glass", "7 Seconds or Less"])
                def_strat = sc2.selectbox("Defense", ["Lockdown Paint", "Full Court Press", "Box Out", "Switch Everything"])
                
                if sc3.button("Simulate Quarter", type="primary"):
                    battle.team1_strat['off'] = off_strat
                    battle.team1_strat['def'] = def_strat
                    opts_off = ["Feed the Hot Hand", "Ball Movement", "Crash the Glass", "7 Seconds or Less"]
                    opts_def = ["Lockdown Paint", "Full Court Press", "Box Out", "Switch Everything"]
                    battle.team2_strat['off'] = random.choice(opts_off)
                    battle.team2_strat['def'] = random.choice(opts_def)
                    
                    rounds = 12
                    for _ in range(rounds):
                        if not battle.team_alive(battle.team1) or not battle.team_alive(battle.team2): break
                        for rank in range(5):
                            if battle.rank_initiative[rank] == 1:
                                battle.sim_lane_action(battle.team1, battle.team2, rank, 1, battle.team1_strat)
                                battle.sim_lane_action(battle.team2, battle.team1, rank, 2, battle.team2_strat)
                            else:
                                battle.sim_lane_action(battle.team2, battle.team1, rank, 2, battle.team2_strat)
                                battle.sim_lane_action(battle.team1, battle.team2, rank, 1, battle.team1_strat)
                                
                    if battle.team_alive(battle.team1) and battle.team_alive(battle.team2):
                        battle.quarter += 1
                    st.rerun()
                
                with st.expander("Game Log", expanded=True):
                    for log in reversed(battle.battle_log[-24:]):
                        st.text(log)