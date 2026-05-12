import logging
from datetime import timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telethon import TelegramClient

logger = logging.getLogger(__name__)
MSK = timezone(timedelta(hours=3))

class JobManager:
    def __init__(self, main_client: TelegramClient, clients: dict, storage):
        self.main_client = main_client  # основной аккаунт бота
        self.clients = clients          # {user_id: персональный клиент}
        self.storage = storage
        self.scheduler = AsyncIOScheduler(timezone=MSK)
        self.scheduler.start()
        self._tcard_jobs = set()
        self._daily_jobs = set()
        self._autofarm_jobs = set()

    async def restore_all(self):
        if not self.main_client:
            return
        for uid_str in self.storage.all_users():
            uid = int(uid_str)
            us = self.storage.get_user(uid)
            if us.get("tcard_enabled"):
                self.add_tcard(uid, us["tcard_interval"])
            if us.get("daily_enabled"):
                self.add_daily(uid)
            if us.get("autofarm_enabled") and uid in self.clients:
                self.add_autofarm(uid)

    # ---------- tcard (общий бот) ----------
    def add_tcard(self, user_id: int, interval: int):
        if not self.main_client:
            return
        jid = f"tcard_{user_id}"
        self._remove_all_with_prefix("tcard_", user_id)
        self.scheduler.add_job(
            self._send_tcard, "interval", minutes=interval,
            id=jid, args=[user_id], replace_existing=True
        )
        self._tcard_jobs.add(user_id)
        logger.info(f"tcard job for {user_id} every {interval} min")

    def remove_tcard(self, user_id: int):
        self._remove_all_with_prefix("tcard_", user_id)
        self._tcard_jobs.discard(user_id)

    async def _send_tcard(self, user_id: int):
        try:
            await self.main_client.send_message(
                __import__("config").GAME_BOT_USERNAME, "ткарточка"
            )
            logger.info(f"tcard sent (user {user_id})")
        except Exception as e:
            logger.error(f"tcard error {user_id}: {e}")

    # ---------- daily (общий бот) ----------
    def add_daily(self, user_id: int):
        if not self.main_client:
            return
        jid = f"daily_{user_id}"
        self._remove_all_with_prefix("daily_", user_id)
        # 10:00 MSK = 7:00 UTC
        self.scheduler.add_job(
            self._daily_present, "cron", hour=7, minute=0,
            id=jid, args=[user_id], replace_existing=True
        )
        self._daily_jobs.add(user_id)

    def remove_daily(self, user_id: int):
        self._remove_all_with_prefix("daily_", user_id)
        self._daily_jobs.discard(user_id)

    async def _daily_present(self, user_id: int):
        try:
            bot = __import__("config").GAME_BOT_USERNAME
            await self.main_client.send_message(bot, "Ежедневная награда")
            async for msg in self.main_client.iter_messages(bot, limit=1):
                if msg.reply_markup:
                    for row in msg.reply_markup.rows:
                        for btn in row.buttons:
                            if "Забрать" in btn.text:
                                await btn.click()
                                return
            logger.info(f"daily present (user {user_id})")
        except Exception as e:
            logger.error(f"daily error {user_id}: {e}")

    # ---------- autofarm (персональные) ----------
    def add_autofarm(self, user_id: int):
        if user_id not in self.clients:
            return
        jid = f"autofarm_{user_id}"
        self._remove_all_with_prefix("autofarm_", user_id)
        self.scheduler.add_job(
            self._do_autofarm, "cron", hour=0, minute=0,
            id=jid, args=[user_id], replace_existing=True
        )
        self._autofarm_jobs.add(user_id)

    def remove_autofarm(self, user_id: int):
        self._remove_all_with_prefix("autofarm_", user_id)
        self._autofarm_jobs.discard(user_id)

    async def _do_autofarm(self, user_id: int):
        client = self.clients.get(user_id)
        if not client:
            return
        us = self.storage.get_user(user_id)
        target = us.get("target")
        amount = us.get("amount") or 0
        try:
            bot = __import__("config").GAME_BOT_USERNAME
            await client.send_message(bot, "/tfarm")
            async for msg in client.iter_messages(bot, limit=3):
                if msg.reply_markup:
                    for row in msg.reply_markup.rows:
                        for btn in row.buttons:
                            if "Забрать деньги с фермы" in btn.text:
                                await btn.click()
                                break
            if target and amount >= 1:
                await client.send_message(bot, f"/pay {target} {amount}")
            logger.info(f"autofarm done for {user_id}")
        except Exception as e:
            logger.error(f"autofarm error {user_id}: {e}")

    def _remove_all_with_prefix(self, prefix: str, user_id: int):
        suffix = f"_{user_id}"
        to_remove = [job.id for job in self.scheduler.get_jobs()
                     if job.id.startswith(prefix) and job.id.endswith(suffix)]
        for jid in to_remove:
            try:
                self.scheduler.remove_job(jid)
            except Exception:
                pass

    def shutdown(self):
        self.scheduler.shutdown(wait=False)