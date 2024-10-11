import os
import asyncio
from discord.ext import tasks
import config
from services.server_status import ServerStatusService
import logging

# Configure the logging module for better performance and flexibility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MinecraftLogWatcher:
    def __init__(self, bot):
        self.bot = bot
        self.log_file_path = config.LOG_FILE_PATH
        self.channel_id = config.CONSOLE_CHANNEL_ID
        self.last_known_size = self.get_log_size()  # Start with current file size
        self.buffer = []  # Buffer for log changes
        self.debounce_task = None  # Task for debouncing on_log_change
        self.debounce_time = 5  # Debounce time in seconds
        self.message_limit = 20  # Limit to bundle multiple log entries
        self.initial_load = True  # Flag to identify initial log processing
        self.max_buffer_size = 100  # Maximum size of the buffer
        self.lock = asyncio.Lock()  # Lock to prevent concurrent on_log_change calls

        if self.log_file_path:
            self.watch_log.start()
            self.flush_buffer.start()  # Task to regularly flush the buffer

    def get_log_size(self):
        try:
            return os.stat(self.log_file_path).st_size
        except FileNotFoundError:
            logger.warning("Log file not found. Setting initial size to 0.")
            return 0

    @tasks.loop(seconds=2)  # Reduced frequency for better performance
    async def watch_log(self):
        try:
            current_size = os.stat(self.log_file_path).st_size

            if current_size < self.last_known_size:
                logger.info("Log file was reset. Ignoring previous entries.")
                self.last_known_size = current_size  # Reset the known size

            elif current_size > self.last_known_size:
                logger.info("New log entries detected.")
                await self.process_log()
                self.last_known_size = (
                    current_size  # Update the known size after processing
                )

            else:
                logger.debug("No new entries in the log file.")

        except FileNotFoundError:
            logger.warning("Log file not found. Waiting for it to be created...")

    def is_relevant_line(self, line):
        # Determines if a log line is relevant and should trigger actions
        irrelevant_keywords = ["RCON", "Paper Watchdog Thread"]
        if any(keyword in line for keyword in irrelevant_keywords):
            return False
        stripped_line = line.strip()
        if not stripped_line:
            return False
        # Add any additional filters here
        return True

    async def process_log(self):
        # Processes new log entries and bundles them for sending
        try:
            logger.debug("Processing log entries...")
            new_lines = []  # Collect new log lines for bundling

            with open(self.log_file_path, "r") as file:
                file.seek(self.last_known_size)
                while True:
                    line = file.readline()
                    if not line:
                        break  # No more new lines, stop reading
                    if self.is_relevant_line(line):
                        stripped_line = line.strip()
                        new_lines.append(stripped_line)
                        self.buffer.append(stripped_line)

                        # Limit the buffer size to prevent excessive memory usage
                        if len(self.buffer) > self.max_buffer_size:
                            self.buffer.pop(0)
                        logger.debug(f"Added relevant line: {stripped_line}")
                    else:
                        logger.debug(f"Ignored line: {line.strip()}")

            # Directly send small sets of messages
            if 0 < len(new_lines) <= 5:
                await self.flush_buffer(immediate=True)

            # Start debounce only if there are new relevant lines and not during initial load
            if new_lines and not self.initial_load:
                if self.debounce_task and not self.debounce_task.done():
                    self.debounce_task.cancel()
                    logger.debug("Debounce timer reset due to new changes.")
                self.debounce_task = self.bot.loop.create_task(
                    self.debounce_on_log_change()
                )

            # End the initial load phase after the first processing
            if self.initial_load:
                self.initial_load = False

        except Exception as e:
            logger.error(f"Error processing the log file: {e}")

    async def debounce_on_log_change(self):
        # Debounced call to `on_log_change`, resets the timer if further changes occur
        try:
            await asyncio.sleep(self.debounce_time)  # Wait for the debounce period
            async with self.lock:
                logger.info("Debounce period elapsed, calling `on_log_change()`.")
                await ServerStatusService(
                    self.bot
                ).on_log_change()  # Trigger the log change
                logger.info("`on_log_change()` has been called successfully.")
        except asyncio.CancelledError:
            logger.debug("Debounce timer was reset.")
        except Exception as e:
            logger.error(f"Error in debounce_on_log_change: {e}")
        finally:
            self.debounce_task = None  # Reset the debounce task

    @tasks.loop(seconds=5)  # Optimized frequency for buffer flushing
    async def flush_buffer(self, immediate=False):
        # Processes the buffer either immediately or on a schedule
        if self.buffer:
            try:
                logger.debug("Flushing the buffer...")
                channel = self.bot.get_channel(self.channel_id)
                if channel:
                    while self.buffer:
                        batch = self.buffer[: self.message_limit]
                        message = "\n".join(batch)
                        await channel.send(message)
                        self.buffer = self.buffer[self.message_limit :]
            except Exception as e:
                logger.error(f"Error sending messages to Discord: {e}")

    @watch_log.before_loop
    async def before_watch_log(self):
        await self.bot.wait_until_ready()
