import asyncio
import datetime
import logging
from asyncio import Queue
from asyncio.streams import StreamReader

import aiofiles
import configargparse

import gui

logger = logging.getLogger(__name__)


def parse_cli_args():
    parser = configargparse.ArgumentParser(default_config_files=['./reader_config.cfg'])
    parser.add('--host', help='Chat host')
    parser.add('--port', help='Chat port')
    parser.add('--history', help='Where to save chat history')
    return parser


async def connect_to_chat(chat_queue: Queue, log_queue: Queue, reader: StreamReader, history_location: str):
    await read_messages_from_history(chat_queue, history_location)
    while True:
        message = await get_message(reader)
        chat_queue.put_nowait(message)
        log_queue.put_nowait(message)


async def save_messages(queue: Queue, path):
    while True:
        async with aiofiles.open(path, mode='a', encoding='utf-8') as file:
            message = await queue.get()
            await file.writelines(message)


async def read_messages_from_history(queue: Queue, path: str):
    async with aiofiles.open(path, mode='r', encoding='utf-8') as file:
        async for message in file:
            queue.put_nowait(message)


async def get_message(reader: StreamReader):
    chat_message = await reader.readline()
    message_time = datetime.datetime.now().strftime('%d.%m.%y %H:%M')
    decoded_message = chat_message.decode()
    return f'[{message_time}] {decoded_message}'


async def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.DEBUG,
        filename='read_chat.log',
    )

    config = parse_cli_args().parse_args()

    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    history_queue = asyncio.Queue()

    logger.debug('Connecting to chat')

    logger.debug(config)
    chat_host = config.host
    chat_port = config.port
    history_location = config.history

    reader, writer = await asyncio.open_connection(
        chat_host, chat_port,
    )

    gui_task = gui.draw(messages_queue, sending_queue, status_updates_queue)
    sending_messages_task = connect_to_chat(messages_queue, history_queue, reader, history_location)
    saving_history_task = save_messages(history_queue, history_location)

    await asyncio.gather(gui_task, sending_messages_task, saving_history_task)


if __name__ == '__main__':
    asyncio.run(main())
