import asyncio
from typing import Optional
from models import QueueEntry

class HelpQueue:
    def __init__(self):
        self.entries: list[QueueEntry] = []
        self.lock = asyncio.Lock()
        self.is_open = False

    async def add(self, entry: QueueEntry):
        async with self.lock:
            self.entries.append(entry)

    async def remove(self, user_id: int):
        async with self.lock:
            self.entries = [
                e for e in self.entries if e.user_id != user_id
            ]

    async def get_position(self, user_id: int) -> Optional[int]:
        async with self.lock:
            for i, e in enumerate(self.entries):
                if e.user_id == user_id:
                    return i + 1
        return None
    
    async def is_in_queue(self, user_id: int):
        async with self.lock:
            for entry in self.entries:
                if entry.user_id == user_id:
                    return True
        return False

    async def next(self, passoff_only=False) -> Optional[QueueEntry]:
        async with self.lock:
            if passoff_only:
                for i, e in enumerate(self.entries):
                    if e.is_passoff:
                        return self.entries.pop(i)

            return self.entries.pop(0) if self.entries else None

    async def view(self) -> str:
        async with self.lock:
            if not self.entries:
                return "Queue is empty."

            out = ["Students in queue:\n"]
            for i, e in enumerate(self.entries, start=1):
                tag = "PASSOFF" if e.is_passoff else "HELP"
                out.append(f"{i}. {e.username} - {tag} - {e.question}")

            return "\n".join(out)