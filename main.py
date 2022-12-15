import asyncio
import datetime
import logging

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


async def connect_to_chat(queue, config):
    logger.debug('Connecting to chat')

    logger.debug(config)
    chat_host = config.host
    chat_port = config.port
    history_location = config.history

    reader, writer = await asyncio.open_connection(
        chat_host, chat_port,
    )

    while True:
        chat_message = await reader.readline()
        message_time = datetime.datetime.now().strftime('%d.%m.%y %H:%M')
        decoded_message = chat_message.decode()
        message_with_timestamp = f'[{message_time}] {decoded_message}'

        async with aiofiles.open(history_location, mode='a', encoding='utf-8') as file:
            await file.writelines(message_with_timestamp)

        queue.put_nowait(message_with_timestamp)


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

    gui_task = gui.draw(messages_queue, sending_queue, status_updates_queue)
    messages_task = connect_to_chat(messages_queue, config)
    await asyncio.gather(gui_task, messages_task)


if __name__ == '__main__':
    asyncio.run(main())
