"""Shared CSV import/export helpers — column-mapping import is a two-step
flow (preview, then commit) so the frontend can show the user a mapping UI
between those steps; export is a single streamed response.

`CsvImportExportMixin` bolts all four endpoints (export, import/template,
import/preview, import/commit) onto any ModelViewSet whose model has its
own `owner` FK (true of nearly every model in this app — the multi-tenant
pattern used throughout). A subclass only declares what's specific to it —
which columns, which are required, one example row, how to render a row for
export — instead of reimplementing the parsing/validation loop each time.
"""

import csv
import io

from django.http import HttpResponse
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

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
    matched case/whitespace/punctuation-insensitively against the field
    name, its full human label, or the label's lead-in before any
    parenthetical (e.g. "Type" still matches "Type (Damage, Repair, ...)"
    — labels here often carry inline format/choice hints for the mapping
    dropdown and template header, which a short real-world column name
    like "Type" or "Status" wouldn't otherwise match). Unmatched columns
    are left out — the frontend treats missing entries as "ignore this
    column"."""

    def normalize(s: str) -> str:
        return ''.join(ch for ch in s.lower() if ch.isalnum())

    lookup = {}
    for field, label in field_labels.items():
        lookup[normalize(field)] = field
        lookup[normalize(label)] = field
        lookup[normalize(label.split('(')[0])] = field

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


def normalize_date_like(raw_value: str, *, as_datetime: bool = False) -> str:
    """Best-effort parse of a date/datetime string in almost any common
    shape — ISO, US M/D/Y, D-M-Y, month names, whatever Excel/Sheets
    happened to export in the user's regional format — into the ISO 8601
    string DRF's DateField/DateTimeField actually accept. People preparing
    a CSV by hand rarely type YYYY-MM-DD; rejecting everything else makes
    bulk import fragile for exactly the audience it's meant to help.
    Returns the original string unchanged if it can't confidently be
    parsed as a date at all, so DRF's own validation error still surfaces
    with a clear message rather than silently passing through garbage."""
    from dateutil import parser as dateutil_parser

    try:
        # dayfirst=False: ambiguous all-numeric dates (e.g. "4/12/2025")
        # are read month-first (US convention) — the common case for this
        # app's existing data/sample rows. Unambiguous formats (ISO, or
        # anything with a month name) parse correctly regardless.
        parsed = dateutil_parser.parse(raw_value, dayfirst=False)
    except (ValueError, OverflowError, TypeError):
        return raw_value
    return parsed.isoformat() if as_datetime else parsed.date().isoformat()


def resolve_related(model, owner_id, raw_value: str, *, match_fields: list[str], label: str):
    """Looks up a related object by trying each of `match_fields` in order
    (case-insensitive exact match) — e.g. an Employee referenced by email or
    name in a CSV column, since nobody importing data from a spreadsheet
    knows (or should need to know) internal database IDs. Returns
    (pk, None) on a match, (None, error_message) otherwise."""
    if not raw_value:
        return None, None
    qs = model.objects.filter(owner_id=owner_id)
    for field in match_fields:
        obj = qs.filter(**{f'{field}__iexact': raw_value}).first()
        if obj:
            return obj.pk, None
    return None, f'{label} "{raw_value}" not found — check the spelling matches exactly'


def resolve_employee(owner_id, raw_value: str):
    """Shared across every app whose CSV imports reference an employee
    (people, talent, payroll_benefits, it_assets) — matched by email first
    (more likely unique), falling back to full name."""
    from people.models import Employee

    return resolve_related(Employee, owner_id, raw_value, match_fields=['email', 'name'], label='Employee')


class CsvImportExportMixin:
    """Adds GET .../export/, GET .../import/template/, POST
    .../import/preview/, and POST .../import/commit/ to a ModelViewSet.

    Subclasses set:
      csv_filename          'candidates' -> candidates.csv / candidates-import-template.csv
      csv_import_fields      {model_field: 'Column Label'} — the label is
                              shown in the mapping dropdown and as the
                              template's header, so make it self-explanatory
                              (e.g. 'Employee (name or email)' for a field
                              that goes through a resolver).
      csv_required_fields    subset of csv_import_fields keys
      csv_export_header      column labels for the full data export
      csv_sample_row         one example row (list of str) written under the
                              header in the template, so the expected format/
                              choices/date-shape are obvious without reading
                              docs
      csv_activity_label     e.g. 'candidates', used in the "Imported N
                              <label> from CSV" activity-log line
      csv_field_parsers      {model_field: callable(owner_id, raw_value) ->
                              (value, error_or_None)} — for anything beyond a
                              plain string: FK lookups (resolve_employee /
                              resolve_related) or type coercion (e.g. a
                              pipe-separated list). Only called for fields
                              that were actually present in the row.
    and implement:
      csv_export_row(self, obj) -> list
    """

    csv_filename = 'records'
    csv_import_fields: dict = {}
    csv_required_fields: list = []
    csv_export_header: list = []
    csv_sample_row: list = []
    csv_activity_label = 'records'
    csv_field_parsers: dict = {}

    def csv_export_row(self, obj):
        raise NotImplementedError

    def get_csv_export_queryset(self):
        return self.get_queryset()

    @action(detail=False, methods=['get'])
    def export(self, request):
        rows = [self.csv_export_row(obj) for obj in self.get_csv_export_queryset()]
        return csv_response(f'{self.csv_filename}.csv', self.csv_export_header, rows)

    @action(detail=False, methods=['get'], url_path='import/template')
    def import_template(self, request):
        """A CSV with the header row plus one filled-in example row, so the
        expected columns *and* their format/choices/shape are visible before
        uploading a real file — separate from `export`, which dumps actual
        data."""
        sample = [self.csv_sample_row] if self.csv_sample_row else []
        return csv_response(
            f'{self.csv_filename}-import-template.csv', list(self.csv_import_fields.values()), sample
        )

    @action(detail=False, methods=['post'], url_path='import/preview', parser_classes=[MultiPartParser, FormParser])
    def import_preview(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            columns, rows = parse_csv_upload(upload)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'columns': columns,
                'rows': rows,
                'row_count': len(rows),
                'suggested_mapping': suggest_mapping(columns, self.csv_import_fields),
                'fields': self.csv_import_fields,
                'required_fields': self.csv_required_fields,
            }
        )

    @action(detail=False, methods=['post'], url_path='import/commit', parser_classes=[JSONParser])
    def import_commit(self, request):
        from core.activity import log_activity
        from core.permissions import owner_scope_id

        columns = request.data.get('columns')
        rows = request.data.get('rows')
        mapping = request.data.get('mapping')
        if not isinstance(columns, list) or not isinstance(rows, list) or not isinstance(mapping, dict):
            return Response(
                {'detail': 'Expected {columns, rows, mapping} from the preview step.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_fields = set(self.csv_import_fields)
        mapping = {k: v for k, v in mapping.items() if v in valid_fields}
        mapped_fields = set(mapping.values())
        missing_required = [f for f in self.csv_required_fields if f not in mapped_fields]
        if missing_required:
            labels = [self.csv_import_fields[f] for f in missing_required]
            return Response(
                {'detail': f'Map a column to the required field(s): {", ".join(labels)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer_class = self.get_serializer_class()
        owner_id = owner_scope_id(request)

        # Auto-detect which importable fields are dates/datetimes on the
        # model, so free-form date text (M/D/Y, D-M-Y, month names, ...)
        # gets normalized to ISO before validation instead of just failing.
        probe_fields = serializer_class(context={'request': request}).fields
        date_fields = {
            name: isinstance(field, drf_serializers.DateTimeField)
            for name, field in probe_fields.items()
            if name in self.csv_import_fields
            and isinstance(field, (drf_serializers.DateField, drf_serializers.DateTimeField))
        }

        created = 0
        errors = []
        for i, row in enumerate(rows, start=2):  # row 1 is the header
            record = row_to_record(columns, row, mapping)
            # Blank optional cells shouldn't override a model default (e.g.
            # an empty "Status" column should still fall back to the
            # model's default, not fail validation as an empty string) —
            # only pass through values that were actually provided.
            record = {k: v for k, v in record.items() if v != ''}

            missing = [f for f in self.csv_required_fields if not record.get(f)]
            if missing:
                labels = [self.csv_import_fields[f] for f in missing]
                errors.append(f'Row {i}: {", ".join(labels)} is required')
                continue

            for field, as_datetime in date_fields.items():
                if field in record:
                    record[field] = normalize_date_like(record[field], as_datetime=as_datetime)

            resolve_error = None
            for field, parser in self.csv_field_parsers.items():
                if field in record:
                    parsed, err = parser(owner_id, record[field])
                    if err:
                        resolve_error = err
                        break
                    record[field] = parsed
            if resolve_error:
                errors.append(f'Row {i}: {resolve_error}')
                continue

            serializer = serializer_class(data=record, context={'request': request})
            if not serializer.is_valid():
                first_field, first_errors = next(iter(serializer.errors.items()))
                errors.append(f'Row {i}: {first_field} — {first_errors[0]}')
                continue

            serializer.save(owner_id=owner_id)
            created += 1

        if created:
            log_activity(owner_id, f'Imported {created} {self.csv_activity_label} from CSV', 'neutral')

        return Response({'created': created, 'errors': errors})
