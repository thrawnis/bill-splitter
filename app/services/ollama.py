import base64
import json
from pathlib import Path

import httpx

from ..config import settings

PROMPT = """Examine this receipt image and extract every purchased line item.
Respond with ONLY a JSON array — no markdown, no explanation, nothing else.
Format: [{"name": "Item Name", "price": 9.99, "quantity": 1}]
Rules:
- price is the per-unit price (not multiplied by quantity)
- Skip tax, tip, subtotal, total, and discount lines
- Skip items you cannot read clearly"""


async def parse_receipt(image_path: str) -> list[dict]:
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": PROMPT,
                        "images": [image_b64],
                    }
                ],
            },
        )
        resp.raise_for_status()

    content = resp.json()["message"]["content"].strip()

    start = content.find("[")
    end = content.rfind("]") + 1
    if start == -1 or end == 0:
        return []

    try:
        items = json.loads(content[start:end])
    except json.JSONDecodeError:
        return []
    return [
        {
            "name": str(item.get("name", "Unknown item")).strip(),
            "price": round(float(item.get("price", 0)), 2),
            "quantity": max(1, int(item.get("quantity", 1))),
        }
        for item in items
        if isinstance(item, dict) and float(item.get("price", 0)) > 0
    ]
