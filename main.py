import asyncio
import datetime
import json
import logging
from argparse import Namespace
from asyncio import Queue
from asyncio.streams import StreamReader, StreamWriter

import aiofiles
from configargparse import ArgumentParser

import gui

logger = logging.getLogger(__name__)


def parse_cli_args() -> ArgumentParser:
    parser = ArgumentParser(default_config_files=['./chat_config.cfg'])
    parser.add('--receiver_host', help='Chat host')
    parser.add('--receiver_port', help='Chat port')
    parser.add('--history', help='Where to save chat history')
    parser.add('--sender_host', help='Chat host')
    parser.add('--sender_port', help='Chat port')
    parser.add('--nickname', help='Preferred nickname')
    parser.add('--account_hash', help='Account hash to login')
    return parser


async def run_receiver_connection(
        chat_queue: Queue,
        log_queue: Queue,
        config: Namespace,
):
    logger.debug('Connecting to receiver')
    await read_messages_from_history(chat_queue, config.history)
    reader, writer = await asyncio.open_connection(
        config.receiver_host,
        config.receiver_port,
    )
    while True:
        message = await get_message(reader)
        chat_queue.put_nowait(message)
        log_queue.put_nowait(message)


async def save_messages(queue: Queue, path: str):
    while True:
        async with aiofiles.open(path, mode='a', encoding='utf-8') as file:
            message = await queue.get()
            await file.writelines(message)


async def read_messages_from_history(queue: Queue, path: str):
    async with aiofiles.open(path, mode='r', encoding='utf-8') as file:
        async for message in file:
            queue.put_nowait(message)


async def get_message(reader: StreamReader) -> str:
    chat_message = await reader.readline()
    message_time = datetime.datetime.now().strftime('%d.%m.%y %H:%M')
    decoded_message = chat_message.decode()
    return f'[{message_time}] {decoded_message}'


async def authorize(
        reader: StreamReader,
        writer: StreamWriter,
        queue: Queue,
        account_hash: str
):
    logger.debug('Authorizing')
    message_to_send = f'{account_hash}\n'

    server_reply = await reader.readline()
    logger.debug(server_reply.decode())

    writer.write(message_to_send.encode())
    await writer.drain()

    server_reply_json = await reader.readline()
    logger.debug(server_reply_json.decode())

    if not json.loads(server_reply_json):
        logger.error('Invalid token')
        queue.put_nowait('Неизвестный токен. Проверьте его или зарегистрируйте заново.')


async def send_message(reader, writer, message):
    escaped_message = fr'{message}'
    logger.debug(f'Sending message: \n\t{escaped_message}')

    message_to_send = f'{escaped_message}\n\n'

    writer.write(message_to_send.encode())
    await writer.drain()

    server_reply = await reader.readline()
    logger.debug(server_reply.decode())


async def run_sender_connection(
        reader: StreamReader,
        writer: StreamWriter,
        sending_queue: Queue
):
    while True:
        message = await sending_queue.get()
        await send_message(reader, writer, message)


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
    error_queue = asyncio.Queue()

    logger.debug(config)

    sender_reader, sender_writer = await asyncio.open_connection(
        config.sender_host,
        config.sender_port,
    )

    gui_task = gui.draw(messages_queue, sending_queue, status_updates_queue)
    receiving_messages_task = run_receiver_connection(messages_queue, history_queue, config)
    saving_history_task = save_messages(history_queue, config.history)
    sending_messages_task = run_sender_connection(sender_reader, sender_writer, sending_queue)
    error_task = gui.show_message_box(error_queue)

    await authorize(sender_reader, sender_writer, error_queue, config.account_hash)

    await asyncio.gather(
        sending_messages_task,
        gui_task,
        receiving_messages_task,
        saving_history_task,
        error_task,
    )


if __name__ == '__main__':
    asyncio.run(main())
