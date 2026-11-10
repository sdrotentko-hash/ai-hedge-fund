"""
AI Agents v3.5 - Полная версия (Копировать и вставить целиком)
"""
import logging
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

AI_ENABLED = {
    'analyst': True,
    'skeptic': True,
    'context': True,
    'historian': True,
    'wave': True,
    'pattern_matcher': False,
    'smc_architect': True,
    'accumulation_retest': False, # Выключен по умолчанию
    'executor': True
}

AI_WEIGHTS = {
    'analyst': 1.0,
    'skeptic': 1.0,
    'context': 1.0,
    'historian': 1.0,
    'wave': 1.0,
    'pattern_matcher': 0.5,
    'smc_architect': 1.5
}

class AI_Team:
    def __init__(self):
        pass

    def run_analysis(self, data: dict) -> dict:
        if not data or not data.get('indicators'):
            return {'error': 'Недостаточно данных'}

        results = {}
        df = data.get('df')

        if AI_ENABLED['analyst']: results['analyst'] = self._agent_analyst(data)
        if AI_ENABLED['skeptic']: results['skeptic'] = self._agent_skeptic(data)
        if AI_ENABLED['context']: results['context'] = self._agent_context(data)
        if AI_ENABLED['historian']: results['historian'] = self._agent_historian(data)
        if AI_ENABLED['wave']: results['wave'] = self._agent_wave(data)
        if AI_ENABLED['pattern_matcher'] and df is not None and len(df) >= 100:
            results['pattern_matcher'] = self._agent_pattern_matcher(data, df)
        
        if AI_ENABLED['smc_architect'] and df is not None and len(df) >= 50:
            results['smc_architect'] = self._agent_smc_architect(data, df)
            
            # Ретесты: только информация, вес = 0
            if AI_ENABLED['accumulation_retest']:
                retest_info = self._detect_accumulation_retest(data, df)
                if retest_info:
                    results['smc_architect']['reasons'].append("─" * 30)
                    results['smc_architect']['reasons'].extend(retest_info['reasons'])

        results['executor'] = self._agent_executor(results, data)
        return results

    def _agent_analyst(self, data: dict) -> dict:
        ind = data.get('indicators', {})
        price = ind.get('ema_9', 0)
        score, reasons = 0, []
        vwap = ind.get('vwap', 0)
        if price > vwap: score += 1; reasons.append("Цена выше VWAP")
        else: score -= 1; reasons.append("Цена ниже VWAP")
        
        rsi, stoch_k = ind.get('rsi', 50), ind.get('stoch_k', 50)
        if rsi < 30 and stoch_k < 20: reasons.append("Перепроданность (возможен отскок)")
        elif rsi > 70 and stoch_k > 80: reasons.append("Перекупленность (риск разворота)")
        return {'score': score, 'reasons': reasons, 'verdict': 'Анализ'}

    def _agent_skeptic(self, data: dict) -> dict:
        funding = data.get('funding_rate', 0)
        ls_global = data.get('long_short_ratio', {}).get('global', 1.0)
        ls_top = data.get('long_short_ratio', {}).get('top_traders', 1.0)
        oi_change = data.get('oi_change_percent', 0)
        score, reasons, veto = 0, [], False

        if funding > 0.001: reasons.append(f"Фандинг {funding:.4%}: риск сквиза")
        elif funding < -0.001: reasons.append(f"Фандинг {funding:.4%}: киты собирают ликвидность")
        else: reasons.append("Фандинг нейтральный"); score += 1

        if ls_top > 1.2 and ls_global < 1.0: reasons.append("КИТЫ ПОКУПАЮТ, розница продает"); score += 2
        elif ls_top < 0.8 and ls_global > 1.2: reasons.append("КИТЫ ПРОДАЮТ, розница покупает (ловушка)"); veto = True
        if oi_change > 5: reasons.append(f"OI растет (+{oi_change:.1f}%)"); score += 1
        return {'score': score, 'reasons': reasons, 'veto': veto, 'verdict': 'Риски'}

    def _agent_context(self, data: dict) -> dict:
        ind = data.get('indicators', {})
        score, reasons = 0, []
        price, ema_200, ema_250 = ind.get('ema_9', 0), ind.get('ema_200', 0), ind.get('ema_250', 0)
        if price > ema_200 > ema_250: reasons.append("Тренд ВВЕРХ (EMA 200/250)"); score += 2
        elif price < ema_200 < ema_250: reasons.append("Тренд ВНИЗ (EMA 200/250)"); score -= 2
        else: reasons.append("Рынок в боковике")
        
        hour = datetime.utcnow().hour
        if 7 <= hour <= 16: reasons.append("Лондонская сессия"); score += 1
        elif 12 <= hour <= 21: reasons.append("Нью-Йоркская сессия"); score += 2
        else: reasons.append("Низкая волатильность"); score -= 1
        return {'score': score, 'reasons': reasons, 'verdict': 'Контекст'}

    def _agent_historian(self, data: dict) -> dict:
        ind = data.get('indicators', {})
        roc, atr = ind.get('roc', 0), ind.get('atr_14', 0)
        score, reasons = 0, []
        if abs(roc) > 2.0: reasons.append(f"Быстрое движение (ROC: {roc:.2f}%)")
        elif abs(roc) < 0.5: reasons.append(f"Рынок спит (ROC: {roc:.2f}%)"); score -= 1
        else: reasons.append(f"Нормальная скорость (ROC: {roc:.2f}%)"); score += 1
        if atr > 0: reasons.append(f"Волатильность (ATR): {atr:.4f}")
        return {'score': score, 'reasons': reasons, 'verdict': 'Импульс'}

    def _agent_wave(self, data: dict) -> dict:
        ind = data.get('indicators', {})
        vi_plus, vi_minus = ind.get('vortex_vi_plus', 1.0), ind.get('vortex_vi_minus', 1.0)
        score, reasons, phase = 0, [], "Неопределено"
        if vi_plus > vi_minus and vi_plus > 1.0: phase = "ИМПУЛЬС ВВЕРХ"; reasons.append("VI+ доминирует"); score += 2
        elif vi_minus > vi_plus and vi_minus > 1.0: phase = "ИМПУЛЬС ВНИЗ"; reasons.append("VI- доминирует"); score -= 2
        else: phase = "ФЛЭТ / КОРРЕКЦИЯ"; reasons.append("Vortex переплетен")
        return {'score': score, 'reasons': reasons, 'phase': phase, 'verdict': 'Волны'}

    def _agent_pattern_matcher(self, data: dict, df) -> dict:
        try:
            points = self._find_zigzag(df, 100, 0.01)
            if len(points) < 5: return {'score': 0, 'reasons': ["Мало данных для зигзага"], 'verdict': 'Нет данных'}
            curr = [(p['price'] - min(x['price'] for x in points[-5:])) / (max(x['price'] for x in points[-5:]) - min(x['price'] for x in points[-5:])) for p in points[-5:]]
            best_score, matches, details = 0, 0, ""
            for i in range(len(df) - 200, len(df) - 50):
                hist = self._find_zigzag(df.iloc[i:i+100], 100, 0.01)
                if len(hist) < 5: continue
                h_prices = [p['price'] for p in hist[-5:]]
                h_norm = [(p - min(h_prices)) / (max(h_prices) - min(h_prices)) for p in h_prices]
                corr = np.corrcoef(curr, h_norm)[0, 1]
                if not np.isnan(corr) and corr > 0.75:
                    matches += 1
                    if corr > best_score:
                        best_score = corr
                        fut = df.iloc[i+100 : min(i+120, len(df))]
                        if len(fut) > 0 and fut['close'].iloc[0] > 0:
                            pct = ((fut['close'].iloc[-1] - fut['close'].iloc[0]) / fut['close'].iloc[0]) * 100
                            details = f"Сходство {corr:.0%} с {df.index[i].strftime('%d.%m')}. После: {pct:+.2f}%"
            if best_score > 0.85 and matches >= 2: return {'score': 1.5, 'reasons': [f"Высокое сходство ({best_score:.0%})", details], 'verdict': 'Паттерн'}
            elif best_score > 0.75 and matches >= 1: return {'score': 0.5, 'reasons': [f"Сходство ({best_score:.0%})", details], 'verdict': 'Паттерн'}
            return {'score': 0, 'reasons': ["Аналогий не найдено"], 'verdict': 'Нет паттерна'}
        except: return {'score': 0, 'reasons': ["Ошибка"], 'verdict': 'Сбой'}

    def _find_zigzag(self, df, lookback, min_amp):
        try:
            rec = df.tail(lookback)
            h, l = rec['high'].values, rec['low'].values
            pts, last_type, last_price = [], None, None
            for i in range(2, len(rec) - 2):
                if h[i] > h[i-1] and h[i] > h[i-2] and h[i] > h[i+1] and h[i] > h[i+2]:
                    if (last_type == 'low' and last_price and abs(h[i] - last_price)/last_price >= min_amp) or last_type is None:
                        pts.append({'price': h[i], 'type': 'high'}); last_type, last_price = 'high', h[i]
                elif l[i] < l[i-1] and l[i] < l[i-2] and l[i] < l[i+1] and l[i] < l[i+2]:
                    if (last_type == 'high' and last_price and abs(l[i] - last_price)/last_price >= min_amp) or last_type is None:
                        pts.append({'price': l[i], 'type': 'low'}); last_type, last_price = 'low', l[i]
            return pts
        except: return []

    def _agent_smc_architect(self, data: dict, df) -> dict:
        try:
            rec = df.tail(50)
            close, high, low = rec['close'].iloc[-1], rec['high'].iloc[-1], rec['low'].iloc[-1]
            swing_high, swing_low = rec['high'].iloc[:-2].max(), rec['low'].iloc[:-2].min()
            score, reasons, event = 0, [], "Нет событий"

            if low < swing_low and close > swing_low: score += 2; event = "🪤 БЫЧИЙ СВИП"; reasons.append("Пробой минимума, но закрытие выше (сбор ликвидности)")
            elif high > swing_high and close < swing_high: score -= 2; event = "🪤 МЕДВЕЖИЙ СВИП"; reasons.append("Пробой максимума, но закрытие ниже")
            elif close > swing_high: score += 1.5; event = "🏗️ BOS ВВЕРХ"; reasons.append("Закрытие выше локального максимума")
            elif close < swing_low: score -= 1.5; event = "🏗️ BOS ВНИЗ"; reasons.append("Закрытие ниже локального минимума")

            ind = data.get('indicators', {})
            if ind.get('ema_9', 0) < ind.get('ema_200', 0) and close > swing_high: score += 2.5; event = "🔄 CHOCH ВВЕРХ"; reasons.append("Смена характера на восходящую")
            elif ind.get('ema_9', 0) > ind.get('ema_200', 0) and close < swing_low: score -= 2.5; event = "🔄 CHOCH ВНИЗ"; reasons.append("Смена характера на нисходящую")

            if not reasons: reasons.append("SMC-структура нейтральна")
            return {'score': score, 'reasons': reasons, 'verdict': event}
        except: return {'score': 0, 'reasons': ["Ошибка SMC"], 'verdict': 'Сбой'}

    def _detect_accumulation_retest(self, data: dict, df) -> dict:
        try:
            rec = df.tail(100)
            rng = rec.iloc[:-30]
            r_high, r_low = rng['high'].max(), rng['low'].min()
            r_size = (r_high - r_low) / r_low
            if r_size > 0.10 or r_size < 0.02: return None
            
            brk = rec.iloc[-30:]
            close = brk['close'].iloc[-1]
            
            if close > r_high:
                tol = r_high * 0.005
                ret = brk[(brk['low'] <= r_high + tol) & (brk['low'] >= r_high - tol)]
                if 0 < len(ret) < len(brk) and ret.iloc[-1]['close'] > r_low:
                    return {'reasons': [f"🔲 Накопление: {r_low:.4f}–{r_high:.4f}", f"💥 Пробой: {r_high:.4f}", f"🔄 Ретест: {ret.iloc[-1]['low']:.4f}", "✅ Уровень удержан (Инфо)"]}
            elif close < r_low:
                tol = r_low * 0.005
                ret = brk[(brk['high'] >= r_low - tol) & (brk['high'] <= r_low + tol)]
                if 0 < len(ret) < len(brk) and ret.iloc[-1]['close'] < r_high:
                    return {'reasons': [f"🔲 Накопление: {r_low:.4f}–{r_high:.4f}", f"💥 Пробой: {r_low:.4f}", f"🔄 Ретест: {ret.iloc[-1]['high']:.4f}", "✅ Уровень удержан (Инфо)"]}
            return None
        except: return None

    def _agent_executor(self, results: dict, data: dict) -> dict:
        total_score, reasons, veto = 0, [], False
        for name, res in results.items():
            if name == 'executor': continue
            if 'score' in res: total_score += res['score'] * AI_WEIGHTS.get(name, 1.0)
            if 'reasons' in res: reasons.extend(res['reasons'])
            if res.get('veto'): veto = True

        if veto: decision, action = "ВЕТО! Сделка отменена.", "NO_TRADE"
        elif total_score >= 4: decision, action = "СИЛЬНЫЙ ЛОНГ.", "LONG"
        elif total_score <= -4: decision, action = "СИЛЬНЫЙ ШОРТ.", "SHORT"
        else: decision, action = "НЕЙТРАЛЬНО. Переждать.", "NO_TRADE"

        ind = data.get('indicators', {})
        price, atr = ind.get('ema_9', 0), ind.get('atr_14', 0)
        df = data.get('df')
        swing = df.tail(50)['low'].min() if action == 'LONG' and df is not None else (df.tail(50)['high'].max() if action == 'SHORT' and df is not None else None)

        entry, sl, tp1, tp2, rr = price, None, None, None, 0
        if action == 'LONG' and swing and atr > 0:
            sl = swing - atr; risk = entry - sl
            if risk > 0: tp1, tp2, rr = entry + (risk * 1.5), entry + (risk * 2.5), 2.5
        elif action == 'SHORT' and swing and atr > 0:
            sl = swing + atr; risk = sl - entry
            if risk > 0: tp1, tp2, rr = entry - (risk * 1.5), entry - (risk * 2.5), 2.5

        return {'total_score': total_score, 'decision': decision, 'action': action, 'all_reasons': reasons, 'veto': veto, 'entry': entry, 'stop_loss': sl, 'take_profit_1': tp1, 'take_profit_2': tp2, 'risk_reward': rr}
