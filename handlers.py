import time
from datetime import datetime, timezone, timedelta
from aiogram import Router, F, types
from telethon import TelegramClient
from telethon.sessions import StringSession

from config import GA_IDS, API_ID, API_HASH
from storage import Storage

router = Router()

def role_hierarchy(user_role: str, required: str) -> bool:
    order = {"ga": 4, "admin": 3, "player": 2, "banned": 0}
    return order.get(user_role, 0) >= order.get(required, 0)

async def reply(msg: types.Message, text: str):
    await msg.answer(text, parse_mode=None)

# ------- /start -------
@router.message(F.text.lower().in_(["/start", ".start", ".старт"]))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    storage: Storage = message.bot.storage
    storage.register_if_absent(user_id)
    user = storage.get_user(user_id)
    role = user["role"]
    conn = "✅" if user["connected"] else "❌"
    text = (
        f"🤖 PGUB\n"
        f"🆔 {user_id} | Роль: {role} | Привязка: {conn}\n"
        f"Для справки: .помощь"
    )
    if not user["connected"]:
        text += "\n⚠️ Привяжите аккаунт командой .привязать SESSION_STRING"
    await reply(message, text)

@router.message(F.text.lower().in_([".помощь", ".help", ".хелп"]))
async def help_cmd(message: types.Message):
    await reply(message, (
        "🤖 PGUB Bot — Список команд\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Игрок (после привязки):\n"
        ".ткарточка вкл/выкл [мин] — авто-карточка\n"
        ".ежедн вкл/выкл — ежедневный бонус\n"
        ".автоферма — автовывод фермы\n"
        ".цель @user — цель перевода\n"
        ".количество <сумма> — сумма перевода\n"
        ".настройки — ваши настройки\n"
        ".привязать <SESSION_STRING> — привязка\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Админ:\n"
        ".дебаг / .айди / .бан / .разбан\n"
        ".ктоадмин / .ктоигрок / .ктоГА\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "ГА:\n"
        ".роль IDTG 10/2/1 — сменить роль\n"
        ".сессии / .удалитьсессию IDTG\n"
    ))

# ------- Игрок (с привязкой) -------
@router.message(F.text.lower().startswith((".ткарточка", ".tcard")))
async def tcard_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if storage.is_banned(user_id):
        return await reply(message, "🚫 Вы заблокированы.")
    if not storage.get_user(user_id)["connected"]:
        return await reply(message, "❌ Сначала привяжите аккаунт (.привязать).")
    parts = message.text.split()
    if len(parts) < 2:
        return await reply(message, "❌ Формат: .ткарточка вкл/выкл [мин]")
    act = parts[1].lower()
    job = message.bot.scheduler
    if act in ("вкл", "on"):
        interval = 120
        if len(parts) >= 3:
            try:
                interval = int(parts[2])
                if interval < 1: raise ValueError
            except ValueError:
                return await reply(message, "❌ Интервал должен быть целым числом минут >0")
        storage.set_user(user_id, "tcard_enabled", True)
        storage.set_user(user_id, "tcard_interval", interval)
        job.add_tcard(user_id, interval)
        await reply(message, f"🃏 Ткарточка включена (каждые {interval} мин).")
    elif act in ("выкл", "off"):
        storage.set_user(user_id, "tcard_enabled", False)
        job.remove_tcard(user_id)
        await reply(message, "🃏 Ткарточка выключена.")
    else:
        await reply(message, "❌ Укажите вкл или выкл.")

@router.message(F.text.lower().startswith((".ежедн", ".everyday")))
async def daily_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if storage.is_banned(user_id):
        return await reply(message, "🚫 Вы заблокированы.")
    if not storage.get_user(user_id)["connected"]:
        return await reply(message, "❌ Сначала привяжите аккаунт.")
    parts = message.text.split()
    if len(parts) < 2:
        return await reply(message, "❌ Формат: .ежедн вкл/выкл")
    act = parts[1].lower()
    job = message.bot.scheduler
    if act in ("вкл", "on"):
        storage.set_user(user_id, "daily_enabled", True)
        job.add_daily(user_id)
        await reply(message, "🎁 Ежедневная награда включена.")
    elif act in ("выкл", "off"):
        storage.set_user(user_id, "daily_enabled", False)
        job.remove_daily(user_id)
        await reply(message, "🎁 Ежедневная награда выключена.")
    else:
        await reply(message, "❌ Укажите вкл или выкл.")

@router.message(F.text.lower().in_([".настройки", ".settings"]))
async def settings_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if storage.is_banned(user_id):
        return await reply(message, "🚫 Вы заблокированы.")
    s = storage.get_user(user_id)
    tcard = f"✅ каждые {s['tcard_interval']} мин" if s['tcard_enabled'] else "❌ выкл"
    daily = "✅ вкл" if s['daily_enabled'] else "❌ выкл"
    autof = "✅ вкл" if s.get('autofarm_enabled') else "❌ выкл"
    conn = "✅" if s['connected'] else "❌"
    amount = s.get('amount') or 0
    await reply(message, (
        f"⚙️ Ваши настройки:\n"
        f"📱 Привязка: {conn}\n"
        f"🎯 Цель: {s.get('target') or 'не задана'}\n"
        f"💰 Сумма: {amount:,} точек\n"
        f"🃏 Ткарточка: {tcard}\n"
        f"🎁 Ежедн. награда: {daily}\n"
        f"🚜 Автоферма: {autof}"
    ))

@router.message(F.text.lower().startswith(".автоферма"))
async def autofarm_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if storage.is_banned(user_id):
        return await reply(message, "🚫 Вы заблокированы.")
    if not storage.get_user(user_id)["connected"]:
        return await reply(message, "❌ Сначала привяжите аккаунт.")
    current = storage.get_user(user_id).get("autofarm_enabled", False)
    new_val = not current
    storage.set_user(user_id, "autofarm_enabled", new_val)
    if new_val:
        message.bot.scheduler.add_autofarm(user_id)
        await reply(message, "🚜 Автоферма включена (ежедневно в 03:00 МСК).")
    else:
        message.bot.scheduler.remove_autofarm(user_id)
        await reply(message, "🚜 Автоферма выключена.")

@router.message(F.text.lower().startswith(".цель"))
@router.message(F.text.lower().startswith(".target"))
async def target_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if not storage.get_user(user_id)["connected"]:
        return await reply(message, "❌ Сначала привяжите аккаунт.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await reply(message, "❌ Укажите @user")
    target = parts[1].strip()
    if not target.startswith("@"):
        return await reply(message, "❌ Юзернейм должен начинаться с @")
    storage.set_user(user_id, "target", target)
    await reply(message, f"🎯 Цель перевода: {target}")

@router.message(F.text.lower().startswith(".количество"))
@router.message(F.text.lower().startswith(".amount"))
async def amount_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if not storage.get_user(user_id)["connected"]:
        return await reply(message, "❌ Сначала привяжите аккаунт.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await reply(message, "❌ Укажите сумму")
    try:
        amt = int(parts[1].strip())
        if amt < 1: raise ValueError
    except:
        return await reply(message, "❌ Сумма должна быть целым положительным числом.")
    storage.set_user(user_id, "amount", amt)
    await reply(message, f"💰 Сумма перевода: {amt:,} точек")

# ------- Привязка аккаунта -------
@router.message(F.text.lower().startswith(".привязать"))
async def bind_session(message: types.Message):
    storage: Storage = message.bot.storage
    user_id = message.from_user.id
    if storage.is_banned(user_id):
        return await reply(message, "🚫 Вы заблокированы.")
    if storage.get_user(user_id)["connected"]:
        return await reply(message, "❌ Ваш аккаунт уже привязан.")
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await reply(message,
            "❌ Используйте: .привязать <SESSION_STRING>\n"
            "Сессию можно получить, запустив session_gen.py на ПК."
        )
    session_str = parts[1].strip()
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    try:
        await client.start()
    except Exception as e:
        return await reply(message, f"❌ Ошибка сессии: {e}")
    storage.set_user(user_id, "connected", True)
    storage.set_user(user_id, "session_string", session_str)
    message.bot.clients[user_id] = client
    us = storage.get_user(user_id)
    job = message.bot.scheduler
    if us.get("tcard_enabled"):
        job.add_tcard(user_id, us["tcard_interval"])
    if us.get("daily_enabled"):
        job.add_daily(user_id)
    if us.get("autofarm_enabled"):
        job.add_autofarm(user_id)
    await reply(message, "✅ Аккаунт привязан! Все функции активированы.")

# ------- Админ -------
@router.message(F.text.lower().in_([".дебаг", ".debug"]))
async def debug_cmd(message: types.Message):
    storage: Storage = message.bot.storage
    if not role_hierarchy(storage.get_role(message.from_user.id), "admin"):
        return await reply(message, "⛔ Нет прав.")
    uptime = time.time() - message.bot.start_time
    h, rem = divmod(int(uptime), 3600)
    m, s = divmod(rem, 60)
    cnt = storage.count_by_roles()
    now = datetime.now(timezone.utc) + timedelta(hours=3)
    sessions = sum(1 for u in storage.all_users() if storage.get_user(int(u))["connected"])
    await reply(message, (
        f"🛠 Отладка\n"
        f"⏱ Аптайм: {h:02}:{m:02}:{s:02}\n"
        f"🕒 Время бота: {now.strftime('%d.%m.%Y %H:%M')} (UTC+3)\n"
        f"👥 Пользователи: ГА {cnt['ga']}, Админ {cnt['admin']}, Игроков {cnt['player']}, Забанено {cnt['banned']}\n"
        f"📱 Активных сессий: {sessions}"
    ))

@router.message(F.text.lower().in_([".айди", ".id"]))
async def id_cmd(message: types.Message):
    await reply(message, f"🆔 Ваш ID: {message.from_user.id}")

@router.message(F.text.lower().in_([".ктоадмин"]))
async def who_admin(message: types.Message):
    storage = message.bot.storage
    if not role_hierarchy(storage.get_role(message.from_user.id), "admin"):
        return await reply(message, "⛔ Нет прав.")
    admins = [u for u in storage.all_users() if storage.get_role(int(u)) == "admin"]
    await reply(message, f"👥 Администраторы: {', '.join(admins) if admins else 'нет'}")

@router.message(F.text.lower().in_([".ктоигрок"]))
async def who_player(message: types.Message):
    storage = message.bot.storage
    if not role_hierarchy(storage.get_role(message.from_user.id), "admin"):
        return await reply(message, "⛔ Нет прав.")
    players = [u for u in storage.all_users() if storage.get_role(int(u)) == "player"]
    await reply(message, f"👥 Игроки: {', '.join(players) if players else 'нет'}")

@router.message(F.text.lower().in_([".ктоГА"]))
async def who_ga(message: types.Message):
    storage = message.bot.storage
    if not role_hierarchy(storage.get_role(message.from_user.id), "admin"):
        return await reply(message, "⛔ Нет прав.")
    gas = [u for u in storage.all_users() if storage.get_role(int(u)) == "ga"]
    await reply(message, f"👥 ГА: {', '.join(gas) if gas else 'нет'}")

@router.message(F.text.lower().startswith((".бан ", ".ban ")))
async def ban_cmd(message: types.Message):
    storage = message.bot.storage
    user_id = message.from_user.id
    role = storage.get_role(user_id)
    if not role_hierarchy(role, "admin"):
        return await reply(message, "⛔ Нет прав.")
    parts = message.text.split()
    if len(parts) < 2:
        return await reply(message, "❌ Укажите ID")
    try:
        target = int(parts[1])
    except ValueError:
        return await reply(message, "❌ ID должен быть числом.")
    target_role = storage.get_role(target)
    if role == "admin" and target_role in ("ga", "admin"):
        return await reply(message, "❌ Администратор не может заблокировать ГА или другого администратора.")
    storage.set_role(target, "banned")
    # Останавливаем и удаляем клиента, если был привязан
    if target in message.bot.clients:
        client = message.bot.clients.pop(target)
        await client.disconnect()
    message.bot.scheduler.remove_tcard(target)
    message.bot.scheduler.remove_daily(target)
    message.bot.scheduler.remove_autofarm(target)
    await reply(message, f"🚫 Пользователь {target} заблокирован.")

@router.message(F.text.lower().startswith((".разбан ", ".unban ")))
async def unban_cmd(message: types.Message):
    storage = message.bot.storage
    user_id = message.from_user.id
    if not role_hierarchy(storage.get_role(user_id), "admin"):
        return await reply(message, "⛔ Нет прав.")
    parts = message.text.split()
    if len(parts) < 2:
        return await reply(message, "❌ Укажите ID")
    try:
        target = int(parts[1])
    except ValueError:
        return await reply(message, "❌ ID должен быть числом.")
    if storage.get_role(target) != "banned":
        return await reply(message, "❌ Пользователь не забанен.")
    storage.set_role(target, "player")
    await reply(message, f"✅ Пользователь {target} разблокирован.")

@router.message(F.text.lower().startswith((".роль ", ".role ")))
async def role_cmd(message: types.Message):
    storage = message.bot.storage
    user_id = message.from_user.id
    role = storage.get_role(user_id)
    if not role_hierarchy(role, "admin"):
        return await reply(message, "⛔ Нет прав.")
    parts = message.text.split()
    if len(parts) < 3:
        return await reply(message, "❌ Формат: .роль ID 10/2/1")
    try:
        target = int(parts[1])
        code = int(parts[2])
    except ValueError:
        return await reply(message, "❌ ID и роль должны быть числами.")
    if role == "admin":
        if code != 1 or target in GA_IDS or storage.get_role(target) in ("ga", "admin"):
            return await reply(message, "❌ Администратор может только разжаловать игроков до player.")
        storage.set_role(target, "player")
        return await reply(message, f"✅ Пользователь {target} теперь player.")
    elif role == "ga":
        role_map = {10: "ga", 2: "admin", 1: "player"}
        if code not in role_map:
            return await reply(message, "❌ Неверный код (10-ГА, 2-админ, 1-игрок).")
        new_role = role_map[code]
        if target in GA_IDS and new_role != "ga":
            return await reply(message, "❌ Нельзя изменить роль фиксированного ГА.")
        storage.set_role(target, new_role)
        # Если понижаем га/админа до игрока, можно остановить его клиент и задачи (опционально)
        await reply(message, f"✅ Пользователь {target} теперь {new_role}.")
    else:
        await reply(message, "⛔ Нет доступа.")

# ------- ГА -------
@router.message(F.text.lower() == ".сессии")
async def sessions_cmd(message: types.Message):
    storage = message.bot.storage
    if storage.get_role(message.from_user.id) != "ga":
        return await reply(message, "⛔ Только для ГА.")
    sessions = storage.get_all_sessions()
    if not sessions:
        return await reply(message, "📭 Нет активных сессий.")
    text = "📋 Активные сессии:\n"
    for uid, _ in sessions:
        text += f"• {uid}\n"
    await reply(message, text)

@router.message(F.text.lower().startswith(".удалитьсессию"))
async def delsession_cmd(message: types.Message):
    storage = message.bot.storage
    if storage.get_role(message.from_user.id) != "ga":
        return await reply(message, "⛔ Только для ГА.")
    parts = message.text.split()
    if len(parts) < 2:
        return await reply(message, "❌ Укажите ID пользователя.")
    try:
        target = int(parts[1])
    except ValueError:
        return await reply(message, "❌ ID должен быть числом.")
    if not storage.get_user(target)["connected"]:
        return await reply(message, "❌ У этого пользователя нет активной сессии.")
    client = message.bot.clients.pop(target, None)
    if client:
        await client.disconnect()
    storage.remove_session(target)
    message.bot.scheduler.remove_tcard(target)
    message.bot.scheduler.remove_daily(target)
    message.bot.scheduler.remove_autofarm(target)
    await reply(message, f"🗑 Сессия пользователя {target} удалена.")

@router.message()
async def catch_banned(message: types.Message):
    if message.bot.storage.is_banned(message.from_user.id):
        await reply(message, "🚫 Вы заблокированы.")