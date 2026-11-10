"""
Main v3.6 - С командой /why (объяснение рисков)
"""
import asyncio, logging, os
from datetime import datetime
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from data_fetcher import DataFetcher
from ai_agents import AI_Team, AI_ENABLED

# Токен берем из переменной окружения (для Render) или из кода (для локального запуска)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '9079907430:AAHddXT02wK1gEpqL6Fdz9Goynvk9SwKdro')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '380308790')

SCAN_INTERVAL, MIN_SCORE = 600, 4

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

TV_BG, COLOR_UP, COLOR_DOWN = '#131722', '#26a69a', '#ef5350'
COLOR_ENTRY, COLOR_SL, COLOR_TP1, COLOR_TP2 = '#FFD700', '#FF4757', '#00d26a', '#00b894'

fetcher, ai_team = DataFetcher(), AI_Team()
bot_state = {
    '1m_enabled': False, '5m_enabled': True, '15m_enabled': True, '1h_enabled': True,
    'auto_scan_enabled': True, 'is_paused': False,
    'pattern_matcher_enabled': False, 'accumulation_retest_enabled': False
}

def generate_chart(coin, tf, data, analysis):
    try:
        df, exec_res = data.get('df'), analysis.get('executor', {})
        if df is None or len(df) < 50: return None
        chart = df.tail(80).copy()
        fig, ax = plt.subplots(figsize=(14, 7), facecolor=TV_BG)
        ax.set_facecolor(TV_BG)
        for i, (_, row) in enumerate(chart.iterrows()):
            col = COLOR_UP if row['close'] >= row['open'] else COLOR_DOWN
            b_bot, b_top = min(row['open'], row['close']), max(row['open'], row['close'])
            if b_top - b_bot > 0: ax.add_patch(plt.Rectangle((i - 0.4, b_bot), 0.8, b_top - b_bot, facecolor=col, edgecolor=col, lw=0.5))
            ax.plot([i, i], [row['low'], b_bot], color=col, lw=0.8)
            ax.plot([i, i], [b_top, row['high']], color=col, lw=0.8)
        
        for val, col, style, lbl in [(exec_res.get('entry'), COLOR_ENTRY, '-', 'ENTRY'), 
                                     (exec_res.get('stop_loss'), COLOR_SL, '--', 'SL'),
                                     (exec_res.get('take_profit_1'), COLOR_TP1, '--', 'TP1'),
                                     (exec_res.get('take_profit_2'), COLOR_TP2, '--', 'TP2')]:
            if val: ax.axhline(y=val, color=col, linewidth=2, linestyle=style, label=f'{lbl}: {val:.2f}', alpha=0.9)
            
        ax.tick_params(colors='white', labelsize=9)
        ax.grid(True, alpha=0.2, color='gray')
        ax.legend(loc='upper left', facecolor=TV_BG, edgecolor='gray', labelcolor='white', fontsize=10)
        ax.set_title(f'{coin}/USDT ({tf}) | {exec_res.get("action", "WAIT")}', color='white', fontsize=14, fontweight='bold')
        ax.set_xlim(-1, len(chart))
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=120, facecolor=TV_BG, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"Chart error: {e}")
        return None

def format_report(coin, tf, analysis):
    data, ind, exec_res = analysis.get('data', {}), analysis.get('indicators', {}), analysis.get('executor', {})
    price = ind.get('ema_9', 0)
    rpt = f"📊 *ИИ-АНАЛИЗ: {coin}/USDT ({tf})*\n💰 Цена: `{price:.2f}`\n\n"
    if exec_res.get('entry') and exec_res.get('stop_loss') and exec_res.get('take_profit_1'):
        rpt += f"🎯 *ТОЧКИ ВХОДА/ВЫХОДА:*\n  📍 Вход: `{exec_res['entry']:.2f}`\n  🛑 SL: `{exec_res['stop_loss']:.2f}`\n  🎯 TP1: `{exec_res['take_profit_1']:.2f}`\n"
        if exec_res.get('take_profit_2'): rpt += f"  🎯 TP2: `{exec_res['take_profit_2']:.2f}`\n"
        rpt += f"  📊 R:R = 1:{exec_res.get('risk_reward', 0):.1f}\n\n"
    
    for name, title in [('analyst', 'ИИ №1 (Аналитик)'), ('skeptic', 'ИИ №2 (Скептик)'), ('context', 'ИИ №3 (Контекст)'), 
                        ('historian', 'ИИ №4 (Историк)'), ('wave', 'ИИ №5 (Волновой)'), ('smc_architect', 'ИИ №9 (SMC-Архитектор)')]:
        if name in analysis:
            rpt += f"🤖 *{title}:*\n"
            if name == 'skeptic' and analysis[name].get('veto'): rpt += "  🚫 *ВЕТО! Ловушка!*\n"
            rpt += "".join([f"  {r}\n" for r in analysis[name].get('reasons', [])])
            rpt += f"  Счёт: {analysis[name].get('score', 0)}\n\n"
            
    rpt += f"🎯 *Управляющий:* {exec_res.get('decision', 'Нет решения')}\nОбщий счёт: {exec_res.get('total_score', 0)}\n\n🕒 {datetime.now().strftime('%H:%M:%S')}"
    return rpt

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("🤖 *ИИ-Хедж-Фонд v3.6*\n\n"
            "*Команды:*\n"
            "/analyze <монета> <ТФ> — полный анализ\n"
            "/why <монета> <ТФ> — почему сделка может не сработать\n"
            "/control — панель управления\n"
            "/status — статус бота\n"
            "/scan — принудительный скан")
    await update.message.reply_text(text, parse_mode='Markdown')

async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await update.message.reply_text("❌ /analyze BTC 15m")
    coin, tf = context.args[0].upper(), context.args[1].lower()
    await update.message.reply_text(f"🧠 Анализирую {coin} на {tf}...")
    try:
        if coin not in fetcher.market_data: await fetcher.update_coin_data(coin)
        data = fetcher.get_data(coin, tf)
        if not data: return await update.message.reply_text(f"❌ Нет данных для {coin} {tf}")
        
        AI_ENABLED['accumulation_retest'] = bot_state['accumulation_retest_enabled']
        analysis = ai_team.run_analysis(data)
        analysis['data'] = data
        
        chart = generate_chart(coin, tf, data, analysis)
        if chart: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=chart, caption=f"📊 {coin}/USDT ({tf})")
        await update.message.reply_text(format_report(coin, tf, analysis), parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ================= НОВАЯ КОМАНДА /why =================
async def cmd_why(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /why: объясняет риски и причины возможных неудач"""
    if len(context.args) < 2:
        return await update.message.reply_text("❌ Использование: /why RENDER 15m")
    
    coin, tf = context.args[0].upper(), context.args[1].lower()
    await update.message.reply_text(f"🧠 Спрашиваю у ИИ, почему сделка может не сработать для {coin} ({tf})...")
    
    try:
        if coin not in fetcher.market_data:
            await fetcher.update_coin_data(coin)
        data = fetcher.get_data(coin, tf)
        if not data:
            return await update.message.reply_text(f"❌ Нет данных для {coin}")
        
        analysis = ai_team.run_analysis(data)
        skeptic = analysis.get('skeptic', {})
        smc = analysis.get('smc_architect', {})
        wave = analysis.get('wave', {})
        context_ai = analysis.get('context', {})
        executor = analysis.get('executor', {})
        
        reply = f"🔍 *ПОЧЕМУ СДЕЛКА МОЖЕТ НЕ СРАБОТАТЬ ({coin}/{tf}):*\n\n"
        
        # Мнение Скептика
        reply += f"🛡️ *ИИ №2 Скептик (Риски):*\n"
        if skeptic.get('veto'):
            reply += "🚫 *ОБНАРУЖЕНА ЛОВУШКА!* Сделка крайне опасна.\n"
        for r in skeptic.get('reasons', []):
            reply += f"• {r}\n"
            
        # Мнение SMC
        reply += f"\n🏗️ *ИИ №9 SMC (Структура):*\n"
        verdict = smc.get('verdict', 'Нет данных')
        if "СВИП" in verdict:
            reply += f"⚠️ {verdict}. Цена может пойти против толпы, чтобы забить стопы.\n"
        elif "CHOCH" in verdict:
            reply += f"⚠️ {verdict}. Старый тренд сломан, движение может быть ложным.\n"
        elif "BOS" in verdict:
            reply += f"✅ {verdict}. Структура подтверждает текущее направление.\n"
        else:
            reply += f"• {verdict}\n"
            
        # Волновой контекст
        reply += f"\n🌊 *ИИ №5 Волновой:*\n"
        reply += f"• {wave.get('phase', 'Неопределено')}\n"
        
        # Контекст
        reply += f"\n🌍 *ИИ №3 Контекст:*\n"
        for r in context_ai.get('reasons', []):
            reply += f"• {r}\n"
        
        # Итоговый вывод
        reply += f"\n💡 *ИТОГОВЫЙ ВЫВОД:*\n"
        total = executor.get('total_score', 0)
        if executor.get('veto'):
            reply += "🚫 *НЕ ВХОДИТЬ.* Обнаружена ловушка. Риск потери депозита очень высок.\n"
        elif abs(total) < 2:
            reply += "⚪ *РЫНОК НЕОПРЕДЕЛЁН.* Сигналы противоречивы. Лучше переждать.\n"
        elif total > 0:
            reply += "🟢 *Шансы на успех есть,* но проверь стоп-лосс и не завышай объём.\n"
        else:
            reply += "🔴 *Давление продавцов.* Если ты в лонге — подумай о выходе.\n"
        
        await update.message.reply_text(reply, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton(f"{'✅' if bot_state['1m_enabled'] else '❌'} 1m", callback_data='t_1m'), InlineKeyboardButton(f"{'✅' if bot_state['5m_enabled'] else '❌'} 5m", callback_data='t_5m')],
        [InlineKeyboardButton(f"{'✅' if bot_state['15m_enabled'] else '❌'} 15m", callback_data='t_15m'), InlineKeyboardButton(f"{'✅' if bot_state['1h_enabled'] else '❌'} 1h", callback_data='t_1h')],
        [InlineKeyboardButton(f"{'🧠✅' if bot_state['pattern_matcher_enabled'] else '🧠❌'} Паттерны", callback_data='t_pm'), InlineKeyboardButton(f"{'🔲✅' if bot_state['accumulation_retest_enabled'] else '🔲❌'} Ретесты", callback_data='t_ar')],
        [InlineKeyboardButton(f"{'⏸️' if bot_state['is_paused'] else '▶️'} {'ПАУЗА' if bot_state['is_paused'] else 'РАБОТАЕТ'}", callback_data='t_pause'), InlineKeyboardButton(f"{'🟢' if bot_state['auto_scan_enabled'] else '🔴'} АВТОСКАН", callback_data='t_auto')]
    ]
    txt = f"🎛️ *УПРАВЛЕНИЕ*\n\n1m: {'ВКЛ' if bot_state['1m_enabled'] else 'ВЫКЛ'} | 5m: {'ВКЛ' if bot_state['5m_enabled'] else 'ВЫКЛ'}\n15m: {'ВКЛ' if bot_state['15m_enabled'] else 'ВЫКЛ'} | 1h: {'ВКЛ' if bot_state['1h_enabled'] else 'ВЫКЛ'}\n\nПаттерны: {'ВКЛ' if bot_state['pattern_matcher_enabled'] else 'ВЫКЛ'}\nРетесты (инфо): {'ВКЛ' if bot_state['accumulation_retest_enabled'] else 'ВЫКЛ'}\n\nСтатус: {'ПАУЗА' if bot_state['is_paused'] else 'РАБОТАЕТ'} | Автоскан: {'ВКЛ' if bot_state['auto_scan_enabled'] else 'ВЫКЛ'}"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last = "Нет"
    if fetcher.coins:
        d = fetcher.get_data(fetcher.coins[0], '5m')
        if d and d.get('last_update'): last = d['last_update'].strftime('%H:%M:%S')
    txt = f"📊 *СТАТУС*\n\nМонет: {len(fetcher.coins)}\nОбновление: {last}\nСтатус: {'ПАУЗА' if bot_state['is_paused'] else 'РАБОТАЕТ'}"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Сканирую...")
    try:
        await run_scan(context.bot)
        await update.message.reply_text("✅ Готово!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mapping = {'t_1m': ('1m', '1m_enabled'), 't_5m': ('5m', '5m_enabled'), 't_15m': ('15m', '15m_enabled'), 't_1h': ('1h', '1h_enabled'),
               't_pm': ('Паттерны', 'pattern_matcher_enabled'), 't_ar': ('Ретесты', 'accumulation_retest_enabled'),
               't_pause': ('Статус', 'is_paused'), 't_auto': ('Автоскан', 'auto_scan_enabled')}
    if q.data in mapping:
        name, key = mapping[q.data]
        bot_state[key] = not bot_state[key]
        status = "ПАУЗА" if key == 'is_paused' and bot_state[key] else ("ВКЛ" if bot_state[key] else "ВЫКЛ")
        await q.edit_message_text(f"✅ {name}: {status}")

async def run_scan(bot):
    AI_ENABLED['accumulation_retest'] = bot_state['accumulation_retest_enabled']
    if bot_state['is_paused']: return
    tfs = [tf for tf, on in [('1m', bot_state['1m_enabled']), ('5m', bot_state['5m_enabled']), ('15m', bot_state['15m_enabled']), ('1h', bot_state['1h_enabled'])] if on]
    if not tfs: return
    if not fetcher.coins: fetcher.get_top_coins_sync()
    await fetcher.update_all_coins()
    found = 0
    for coin in fetcher.coins:
        for tf in tfs:
            try:
                data = fetcher.get_data(coin, tf)
                if not data: continue
                analysis = ai_team.run_analysis(data)
                analysis['data'] = data
                score = analysis.get('executor', {}).get('total_score', 0)
                if abs(score) >= MIN_SCORE:
                    chart = generate_chart(coin, tf, data, analysis)
                    if chart: await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=chart, caption=f"🚨 СИГНАЛ: {coin}/USDT ({tf})")
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=format_report(coin, tf, analysis), parse_mode='Markdown')
                    found += 1
            except: pass
            await asyncio.sleep(0.1)
    logger.info(f"✅ Скан завершен. Сигналов: {found}")

async def auto_scan_loop(bot):
    while True:
        if bot_state['auto_scan_enabled'] and not bot_state['is_paused']:
            try: await run_scan(bot)
            except Exception as e: logger.error(f"Scan error: {e}")
        await asyncio.sleep(SCAN_INTERVAL)

async def post_init(application):
    await fetcher.start()
    application.create_task(auto_scan_loop(application.bot), name="auto_scan")

def main():
    logger.info("🚀 Запуск v3.6...")
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("why", cmd_why))
    app.add_handler(CommandHandler("control", cmd_control))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CallbackQueryHandler(button_handler))
    logger.info("✅ Бот запущен! Напиши /start")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()