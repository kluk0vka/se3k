import asyncio
import random
import uuid

from app.config import settings


class PspDeclined(Exception):
    pass


async def charge(amount_minor: int) -> str:
    await asyncio.sleep(random.uniform(settings.psp_latency_min_ms, settings.psp_latency_max_ms) / 1000)
    if random.random() < settings.psp_decline_rate:
        raise PspDeclined("card declined")
    return f"psp_{uuid.uuid4().hex[:16]}"


async def refund(psp_reference: str, amount_minor: int) -> str:
    await asyncio.sleep(random.uniform(settings.psp_latency_min_ms, settings.psp_latency_max_ms) / 1000)
    return f"rf_{uuid.uuid4().hex[:16]}"
