"""Lead ingestion: raw payload -> adapter -> normalized ``LeadImportData``.

Import submodules directly (``app.ingestion.normalize``, ``app.ingestion.adapters``). No re-exports here:
``app.schemas.lead`` depends on ``normalize`` while ``adapters`` depends on ``app.schemas``, so eager imports in
this package would create an import cycle.
"""
