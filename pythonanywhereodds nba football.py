import logging
import asyncio
import pytz
import requests
import os
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# NBA API
from nba_api.stats.endpoints import scoreboardv2

# --- KONFIGURASI ---
# Ganti TOKEN jika kamu sudah melakukan 'Revoke' di BotFather
TOKEN = '8621903836:AAG1frcKUzC0y110Cuf5r2fbOXM2GozEqDI'
FOOTBALL_API_KEY = '129f979654msh783082d7f6eab02p197906jsn7e1a5e01ed89'
ODDS_API_KEY = '635af92b5902de211d31a698e1ce2938'

# Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

WIB = pytz.timezone('Asia/Jakarta')

# Header User-Agent untuk menghindari blokir firewall
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

# --- FUNGSI NBA ---
def convert_nba_to_wib(game_status_text):
    if "ET" not in game_status_text:
        return game_status_text
    try:
        time_str = game_status_text.replace(' ET', '').strip()
        if len(time_str.split(':')[0]) == 1: time_str = "0" + time_str
        time_obj = datetime.strptime(time_str, '%I:%M %p')
        tz_et = pytz.timezone('America/New_York')
        now_et = datetime.now(tz_et)
        et_full = tz_et.localize(datetime(now_et.year, now_et.month, now_et.day, time_obj.hour, time_obj.minute))
        return et_full.astimezone(WIB).strftime('%H:%M WIB')
    except Exception as e:
        logger.error(f"Error konversi waktu: {e}")
        return game_status_text

# --- HANDLER BOLA ---
async def get_football(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("Mencari jadwal bola... 🌍")
    today = datetime.now(WIB).strftime('%Y-%m-%d')
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": FOOTBALL_API_KEY, 
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
        **HEADERS
    }
    try:
        res = requests.get(url, headers=headers, params={"date": today}, timeout=25)
        res.raise_for_status()
        fixtures = res.json().get('response', [])
        
        if not fixtures:
            await status_msg.edit_text(f"Tidak ada jadwal bola ({today}).")
            return
            
        priority = [1, 2, 3, 4, 5, 39, 140, 61, 78, 135, 10, 132]
        fixtures.sort(key=lambda x: (x['league']['id'] not in priority, x['league']['id']))
        
        msg = f"⚽ **Jadwal Bola ({today})**\n\n"
        for f in fixtures[:10]:
            home, away = f['teams']['home']['name'], f['teams']['away']['name']
            utc_dt = datetime.fromisoformat(f['fixture']['date'].replace('Z', '+00:00'))
            wib_t = utc_dt.astimezone(WIB).strftime('%H:%M WIB')
            msg += f"🌍 {f['league']['name']}\n🥊 **{home}** vs **{away}**\n⏰ `{wib_t}`\n---\n"
        
        await status_msg.edit_text(msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error Bola: {e}")
        await status_msg.edit_text("⚠️ Gagal mengambil data bola. Akun gratis PythonAnywhere mungkin memblokir akses ke API ini.")

# --- HANDLER NBA ---
async def get_nba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("Mengecek NBA... 🏀")
    try:
        today = datetime.now(WIB).strftime('%Y-%m-%d')
        board = scoreboardv2.ScoreboardV2(game_date=today)
        data_dict = board.get_dict()
        games = data_dict['resultSets'][0]['rowSet']
        lines = data_dict['resultSets'][1]['rowSet']
        
        if not games:
            await status_msg.edit_text("Tidak ada NBA hari ini.")
            return
            
        msg = f"🏀 **NBA ({today})**\n\n"
        for i in range(0, len(lines), 2):
            v, h = lines[i], lines[i+1]
            t_wib = convert_nba_to_wib(games[i // 2][4])
            msg += f"🔥 **{v[4]}** vs **{h[4]}**\n⏰ `{t_wib}`\n---\n"
        await status_msg.edit_text(msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error NBA: {e}")
        await status_msg.edit_text("⚠️ Gagal data NBA.stats.nba.com diblokir oleh PythonAnywhere Free Tier.")

# --- HANDLER ODDS ---
async def get_odds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("Cek Odds... 🎰")
    url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
    try:
        res = requests.get(url, params={
            'apiKey': ODDS_API_KEY, 
            'regions': 'us', 
            'markets': 'h2h', 
            'oddsFormat': 'decimal'
        }, headers=HEADERS, timeout=25)
        res.raise_for_status()
        data = res.json()
        
        if not data:
            await status_msg.edit_text("🎰 Odds belum tersedia.")
            return

        msg = "🎰 **NBA Odds (Dibatasi 10)**\n\n"
        for g in data[:10]:
            if not g['bookmakers']: continue
            msg += f"🏀 {g['away_team']} @ {g['home_team']}\n"
            for o in g['bookmakers'][0]['markets'][0]['outcomes']:
                msg += f"🔹 {o['name']}: `{o['price']}`\n"
            msg += "---\n"
        await status_msg.edit_text(msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error Odds: {e}")
        await status_msg.edit_text("⚠️ Gagal mengambil data Odds.")

# --- MAIN ---
def main():
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        
        app.add_handler(CommandHandler('start', lambda u, c: u.message.reply_text("Bot Aktif!\n/bola - Jadwal Bola\n/nba - Jadwal NBA\n/odds - Odds NBA")))
        app.add_handler(CommandHandler('bola', get_football))
        app.add_handler(CommandHandler('nba', get_nba))
        app.add_handler(CommandHandler('odds', get_odds))
        
        print("Bot berjalan di PythonAnywhere...")
        app.run_polling(poll_interval=2.0)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == '__main__':
    main()
