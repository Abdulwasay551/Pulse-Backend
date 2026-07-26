"""Shared CSV import/export helpers — column-mapping import is a two-step
flow (preview, then commit) so the frontend can show the user a mapping UI
between those steps; export is a single streamed response. Generic here so
any module app can reuse it rather than reimplementing CSV parsing."""

import csv
import io

from django.http import HttpResponse

MAX_IMPORT_ROWS = 5000


def parse_csv_upload(uploaded_file) -> tuple[list[str], list[list[str]]]:
    """Reads an uploaded CSV file and returns (columns, rows). Raises
    ValueError on anything that isn't decodable/parseable UTF-8 CSV."""
    try:
        decoded = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('That file doesn\'t look like a UTF-8 encoded CSV.') from exc

    reader = csv.reader(io.StringIO(decoded))
    rows = list(reader)
    if not rows:
        raise ValueError('The file is empty.')

    columns = [c.strip() for c in rows[0]]
    data_rows = rows[1 : 1 + MAX_IMPORT_ROWS]
    return columns, data_rows


def suggest_mapping(columns: list[str], field_labels: dict[str, str]) -> dict[str, str]:
    """Best-effort auto-mapping from CSV column names to model field names,
    matched case/whitespace/punctuation-insensitively against either the
    field name itself or its human label. Unmatched columns are left out —
    the frontend treats missing entries as "ignore this column"."""

    def normalize(s: str) -> str:
        return ''.join(ch for ch in s.lower() if ch.isalnum())

    lookup = {}
    for field, label in field_labels.items():
        lookup[normalize(field)] = field
        lookup[normalize(label)] = field

    mapping = {}
    for column in columns:
        match = lookup.get(normalize(column))
        if match:
            mapping[column] = match
    return mapping


def row_to_record(columns: list[str], row: list[str], mapping: dict[str, str]) -> dict[str, str]:
    """Applies a {csv_column: model_field} mapping to one parsed row,
    producing {model_field: value}. Missing/extra columns in a ragged row
    are handled gracefully (short rows yield '' for the rest)."""
    record = {}
    for i, column in enumerate(columns):
        field = mapping.get(column)
        if not field:
            continue
        value = row[i].strip() if i < len(row) else ''
        record[field] = value
    return record


def csv_response(filename: str, header: list[str], rows: list[list]) -> HttpResponse:
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response
