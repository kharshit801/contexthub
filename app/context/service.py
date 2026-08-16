"""Context layer service - retrieval logic for business context."""

from typing import Any

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.context.models import (
    Asset,
    BusinessDefinition,
    Lineage,
    SchemaInfo,
    TrustSignal,
)
from app.db.connection import get_session


class ContextService:
    """Service for querying the structured business context layer."""

    def __init__(self, session: Session | None = None):
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = get_session(readonly=True)
        return self._session

    def search_assets(self, query: str) -> list[dict[str, Any]]:
        """Search assets by name or description. Returns matching assets with metadata."""
        search_term = f"%{query.lower()}%"
        results = (
            self.session.query(Asset)
            .filter(
                or_(
                    Asset.name.ilike(search_term),
                    Asset.description.ilike(search_term),
                )
            )
            .all()
        )
        return [
            {
                "name": a.name,
                "type": a.asset_type.value,
                "description": a.description,
                "owner": a.owner,
                "schema": a.schema_name,
                "table": a.table_name,
                "column": a.column_name,
            }
            for a in results
        ]

    def get_definition(self, metric_name: str) -> dict[str, Any] | None:
        """Get the business definition for a metric."""
        # Try exact match first
        defn = (
            self.session.query(BusinessDefinition)
            .filter(BusinessDefinition.metric_name == metric_name.lower().replace(" ", "_"))
            .first()
        )

        # Try fuzzy match
        if not defn:
            search_term = f"%{metric_name.lower()}%"
            defn = (
                self.session.query(BusinessDefinition)
                .filter(
                    or_(
                        BusinessDefinition.metric_name.ilike(search_term),
                        BusinessDefinition.display_name.ilike(search_term),
                        BusinessDefinition.definition.ilike(search_term),
                    )
                )
                .first()
            )

        if not defn:
            return None

        return {
            "metric_name": defn.metric_name,
            "display_name": defn.display_name,
            "definition": defn.definition,
            "calculation": defn.calculation,
            "source_table": defn.source_table,
            "source_column": defn.source_column,
            "filter_condition": defn.filter_condition,
            "owner": defn.owner,
            "status": defn.status.value,
            "examples": defn.examples,
            "notes": defn.notes,
        }

    def search_definitions(self, query: str) -> list[dict[str, Any]]:
        """Search all definitions matching a query. Returns multiple results."""
        search_term = f"%{query.lower()}%"
        results = (
            self.session.query(BusinessDefinition)
            .filter(
                or_(
                    BusinessDefinition.metric_name.ilike(search_term),
                    BusinessDefinition.display_name.ilike(search_term),
                    BusinessDefinition.definition.ilike(search_term),
                )
            )
            .all()
        )
        return [
            {
                "metric_name": d.metric_name,
                "display_name": d.display_name,
                "definition": d.definition,
                "calculation": d.calculation,
                "source_table": d.source_table,
                "source_column": d.source_column,
                "filter_condition": d.filter_condition,
                "owner": d.owner,
                "status": d.status.value,
            }
            for d in results
        ]

    def get_trust_signal(self, asset_name: str) -> dict[str, Any] | None:
        """Get trust signal for an asset."""
        signal = (
            self.session.query(TrustSignal)
            .filter(TrustSignal.asset_name == asset_name)
            .first()
        )

        if not signal:
            # Try fuzzy
            search_term = f"%{asset_name.lower()}%"
            signal = (
                self.session.query(TrustSignal)
                .filter(TrustSignal.asset_name.ilike(search_term))
                .first()
            )

        if not signal:
            return None

        return {
            "asset_name": signal.asset_name,
            "trust_level": signal.trust_level.value,
            "reason": signal.reason,
            "certified_by": signal.certified_by,
            "last_validated": signal.last_validated.isoformat() if signal.last_validated else None,
        }

    def get_schema(self, table_name: str) -> list[dict[str, Any]]:
        """Get enriched schema information for a table."""
        results = (
            self.session.query(SchemaInfo)
            .filter(SchemaInfo.table_name == table_name)
            .all()
        )
        return [
            {
                "table": s.table_name,
                "column": s.column_name,
                "data_type": s.data_type,
                "nullable": s.is_nullable,
                "is_primary_key": s.is_primary_key,
                "description": s.description,
                "business_context": s.business_context,
            }
            for s in results
        ]

    def get_lineage(self, asset_name: str) -> list[dict[str, Any]]:
        """Get lineage relationships for an asset (both upstream and downstream)."""
        results = (
            self.session.query(Lineage)
            .filter(
                or_(
                    Lineage.source_asset == asset_name,
                    Lineage.target_asset == asset_name,
                    Lineage.source_asset.ilike(f"%{asset_name}%"),
                    Lineage.target_asset.ilike(f"%{asset_name}%"),
                )
            )
            .all()
        )
        return [
            {
                "source": l.source_asset,
                "target": l.target_asset,
                "relationship_type": l.relationship_type,
                "description": l.description,
            }
            for l in results
        ]

    def get_all_definitions(self) -> list[dict[str, Any]]:
        """Get all business definitions (useful for listing available metrics)."""
        results = self.session.query(BusinessDefinition).all()
        return [
            {
                "metric_name": d.metric_name,
                "display_name": d.display_name,
                "status": d.status.value,
                "owner": d.owner,
                "source_table": d.source_table,
                "source_column": d.source_column,
            }
            for d in results
        ]

    def close(self):
        """Close the session."""
        if self._session:
            self._session.close()
