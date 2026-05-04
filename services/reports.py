from __future__ import annotations

import csv
from io import BytesIO, StringIO

from database.models import Transaction


def build_csv_export(transactions: list[Transaction]) -> BytesIO:
    text_buffer = StringIO()
    writer = csv.writer(text_buffer)
    writer.writerow(["id", "user_id", "amount", "type", "category", "created_at"])

    for item in transactions:
        writer.writerow(
            [
                item.id,
                item.user_id,
                f"{item.amount:.2f}",
                item.type.value,
                item.category,
                item.created_at.isoformat(),
            ]
        )

    binary = BytesIO(text_buffer.getvalue().encode("utf-8-sig"))
    binary.seek(0)
    return binary
