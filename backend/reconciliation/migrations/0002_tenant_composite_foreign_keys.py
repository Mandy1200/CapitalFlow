"""Composite foreign keys that make cross-organization links impossible.

Django has no composite foreign keys, so they are added in SQL. Each child row
must reference a parent row with the *same* organization_id; the parents'
``(id, organization_id)`` unique constraints come from migration 0001.
PostgreSQL only.
"""

from django.db import migrations

COMPOSITE_KEYS = [
    # (table, constraint name, child column, parent table)
    ("reconciliation_lineitem", "line_item_capital_call_same_org_fk", "capital_call_id", "reconciliation_capitalcall"),
    ("reconciliation_lineitem", "line_item_investor_same_org_fk", "investor_entity_id", "reconciliation_investorentity"),
    ("reconciliation_reconciliationmatch", "match_transaction_same_org_fk", "transaction_id", "reconciliation_banktransaction"),
    ("reconciliation_reconciliationmatch", "match_line_item_same_org_fk", "line_item_id", "reconciliation_lineitem"),
]


def _forward(table, name, column, parent):
    return (
        f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}, organization_id) "
        f"REFERENCES {parent} (id, organization_id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED;"
    )


def _reverse(table, name, column, parent):
    return f"ALTER TABLE {table} DROP CONSTRAINT {name};"


class Migration(migrations.Migration):
    dependencies = [("reconciliation", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=_forward(*key), reverse_sql=_reverse(*key)) for key in COMPOSITE_KEYS
    ]
