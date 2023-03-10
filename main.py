import asyncio
import datetime
import json
import logging
from argparse import Namespace
from asyncio import Queue
from asyncio.streams import StreamReader, StreamWriter
from dataclasses import dataclass

import aiofiles
from configargparse import ArgumentParser

import gui

logger = logging.getLogger(__name__)


@dataclass
class ChatQueue:
    messages: Queue = Queue()
    sending: Queue = Queue()
    status_updates: Queue = Queue()
    history: Queue = Queue()
    errors: Queue = Queue()


def parse_cli_args() -> ArgumentParser:
    parser = ArgumentParser(default_config_files=['./chat_config.cfg'])
    parser.add('--receiver_host', help='Receiver chat host')
    parser.add('--receiver_port', help='Receiver chat port')
    parser.add('--history', help='Where to save chat history')
    parser.add('--sender_host', help='Sender chat host')
    parser.add('--sender_port', help='Sender chat port')
    parser.add('--nickname', help='Preferred nickname')
    parser.add('--account_hash', help='Account hash to login')
    return parser


async def run_receiver_connection(
        chat_queue: Queue,
        log_queue: Queue,
        status_queue: Queue,
        config: Namespace,
):
    logger.debug('Connecting to receiver')
    status_queue.put_nowait(gui.ReadConnectionStateChanged.INITIATED)
    await read_messages_from_history(chat_queue, config.history)
    reader, writer = await asyncio.open_connection(
        config.receiver_host,
        config.receiver_port,
    )
    status_queue.put_nowait(gui.ReadConnectionStateChanged.ESTABLISHED)
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
        error_queue: Queue,
        status_queue: Queue,
        account_hash: str
):
    logger.debug('Authorizing')
    message_to_send = f'{account_hash}\n'

    server_reply = await reader.readline()
    logger.debug(server_reply.decode())

    writer.write(message_to_send.encode())
    await writer.drain()

    server_reply_json = await reader.readline()
    decoded_reply = json.loads(server_reply_json)
    logger.debug(decoded_reply)

    if not decoded_reply:
        logger.error('Invalid token')
        error_queue.put_nowait('?????????????????????? ??????????. ?????????????????? ?????? ?????? ?????????????????????????????? ????????????.')

    nickname = decoded_reply.get('nickname')
    status_queue.put_nowait(gui.NicknameReceived(nickname))


async def send_message(
        reader: StreamReader,
        writer: StreamWriter,
        message: str,
):
    escaped_message = fr'{message}'
    logger.debug(f'Sending message: \n\t{escaped_message}')

    message_to_send = f'{escaped_message}\n\n'

    writer.write(message_to_send.encode())
    await writer.drain()

    server_reply = await reader.readline()
    logger.debug(server_reply.decode())


async def run_sending_queue(
        reader: StreamReader,
        writer: StreamWriter,
        queue: Queue
):
    while True:
        message = await queue.get()
        await send_message(reader, writer, message)


async def run_sender_connection(
        queue: Queue,
        config: Namespace,
):
    queue.put_nowait(gui.SendingConnectionStateChanged.INITIATED)
    reader, writer = await asyncio.open_connection(
        config.sender_host,
        config.sender_port,
    )
    queue.put_nowait(gui.SendingConnectionStateChanged.ESTABLISHED)
    return reader, writer


async def run_tasks(
        reader: StreamReader,
        writer: StreamWriter,
        config: Namespace,
        chat_queue: ChatQueue,
):
    gui_task = gui.draw(
        chat_queue.messages,
        chat_queue.sending,
        chat_queue.status_updates,
    )
    receiving_messages_task = run_receiver_connection(
        chat_queue.messages,
        chat_queue.history,
        chat_queue.status_updates,
        config,
    )
    saving_history_task = save_messages(
        chat_queue.history,
        config.history,
    )
    sending_messages_task = run_sending_queue(
        reader,
        writer,
        chat_queue.sending,
    )
    error_task = gui.show_message_box(chat_queue.errors)

    await asyncio.gather(
        sending_messages_task,
        gui_task,
        receiving_messages_task,
        saving_history_task,
        error_task,
    )


async def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.DEBUG,
        filename='technical.log',
    )

    config = parse_cli_args().parse_args()
    logger.debug(config)

    chat_queue = ChatQueue()
    sender_reader, sender_writer = await run_sender_connection(chat_queue.status_updates, config)

    await authorize(
        sender_reader,
        sender_writer,
        chat_queue.errors,
        chat_queue.status_updates,
        config.account_hash,
    )
    await run_tasks(sender_reader, sender_writer, config, chat_queue)


if __name__ == '__main__':
    asyncio.run(main())
