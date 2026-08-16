"""Context layer models - structured business metadata stored in PostgreSQL."""

import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.connection import Base


class AssetType(str, enum.Enum):
    TABLE = "table"
    COLUMN = "column"
    METRIC = "metric"
    DASHBOARD = "dashboard"


class TrustLevel(str, enum.Enum):
    CERTIFIED = "certified"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    STALE = "stale"


class MetricStatus(str, enum.Enum):
    CERTIFIED = "certified"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    DRAFT = "draft"


# --- Context Tables ---


class Asset(Base):
    """Metadata about data assets (tables, columns, metrics)."""

    __tablename__ = "assets"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(100), default="business")
    table_name: Mapped[str | None] = mapped_column(String(255))
    column_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BusinessDefinition(Base):
    """Business metric definitions with ownership and certification status."""

    __tablename__ = "business_definitions"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    calculation: Mapped[str | None] = mapped_column(Text)
    source_table: Mapped[str] = mapped_column(String(255), nullable=False)
    source_column: Mapped[str] = mapped_column(String(255), nullable=False)
    filter_condition: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[MetricStatus] = mapped_column(Enum(MetricStatus), nullable=False)
    examples: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class TrustSignal(Base):
    """Trust signals for data assets - indicates reliability and certification."""

    __tablename__ = "trust_signals"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trust_level: Mapped[TrustLevel] = mapped_column(Enum(TrustLevel), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    certified_by: Mapped[str | None] = mapped_column(String(255))
    last_validated: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SchemaInfo(Base):
    """Enriched schema information with business descriptions for columns."""

    __tablename__ = "schema_info"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(100), nullable=False)
    is_nullable: Mapped[bool] = mapped_column(default=True)
    is_primary_key: Mapped[bool] = mapped_column(default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    business_context: Mapped[str | None] = mapped_column(Text)


class Lineage(Base):
    """Data lineage - relationships between assets."""

    __tablename__ = "lineage"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_asset: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_asset: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
