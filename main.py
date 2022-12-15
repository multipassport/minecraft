import asyncio
import time

import gui


async def generate_messages(queue: asyncio.Queue) -> None:
    while True:
        message = time.time()
        queue.put_nowait(message)
        await asyncio.sleep(1)


async def main():
    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()

    gui_task = gui.draw(messages_queue, sending_queue, status_updates_queue)
    messages_task = generate_messages(messages_queue)
    await asyncio.gather(gui_task, messages_task)


if __name__ == '__main__':
    asyncio.run(main())
