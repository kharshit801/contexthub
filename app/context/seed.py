"""Seed the context layer with business definitions, metadata, trust signals, and lineage."""

from datetime import datetime

from sqlalchemy import text

from app.context.models import (
    Asset,
    AssetType,
    BusinessDefinition,
    Lineage,
    MetricStatus,
    SchemaInfo,
    TrustLevel,
    TrustSignal,
)
from app.db.connection import Base, get_engine, get_session


def seed_assets(session) -> None:
    """Seed asset metadata."""
    assets = [
        # Tables
        Asset(
            name="customers",
            asset_type=AssetType.TABLE,
            description="Master customer table containing all registered customers across segments",
            owner="Customer Success Team",
            schema_name="business",
            table_name="customers",
        ),
        Asset(
            name="orders",
            asset_type=AssetType.TABLE,
            description="All customer orders with financial breakdowns. Contains multiple amount fields - use business definitions to determine which represents revenue.",
            owner="Finance Team",
            schema_name="business",
            table_name="orders",
        ),
        Asset(
            name="products",
            asset_type=AssetType.TABLE,
            description="Product catalog with pricing. base_price is the list price before any customer-specific adjustments.",
            owner="Product Team",
            schema_name="business",
            table_name="products",
        ),
        Asset(
            name="payments",
            asset_type=AssetType.TABLE,
            description="Payment transactions linked to orders. One payment per order. Status reflects payment outcome.",
            owner="Finance Team",
            schema_name="business",
            table_name="payments",
        ),
        # Key metrics as assets
        Asset(
            name="net_revenue",
            asset_type=AssetType.METRIC,
            description="The company's certified revenue metric. Maps to orders.net_amount for completed orders only.",
            owner="Finance Team",
            schema_name="business",
            table_name="orders",
            column_name="net_amount",
        ),
        Asset(
            name="gross_revenue",
            asset_type=AssetType.METRIC,
            description="DEPRECATED. Previously used total_amount as revenue. Does not account for discounts or refunds.",
            owner="Finance Team",
            schema_name="business",
            table_name="orders",
            column_name="total_amount",
        ),
        Asset(
            name="active_customer_count",
            asset_type=AssetType.METRIC,
            description="Count of customers with is_active=true AND at least one order in the last 90 days.",
            owner="Customer Success Team",
            schema_name="business",
            table_name="customers",
            column_name="is_active",
        ),
        Asset(
            name="customer_count",
            asset_type=AssetType.METRIC,
            description="Total count of all registered customers regardless of activity status.",
            owner="Customer Success Team",
            schema_name="business",
            table_name="customers",
        ),
    ]
    for asset in assets:
        session.add(asset)
    session.flush()


def seed_business_definitions(session) -> None:
    """Seed business metric definitions - the core of what makes ContextHub valuable."""
    definitions = [
        BusinessDefinition(
            metric_name="net_revenue",
            display_name="Net Revenue",
            definition="Total revenue from completed orders after all adjustments. This is the company's official revenue metric used in financial reporting.",
            calculation="SUM(orders.net_amount) WHERE orders.status = 'completed'",
            source_table="business.orders",
            source_column="net_amount",
            filter_condition="status = 'completed'",
            owner="Finance Team",
            status=MetricStatus.CERTIFIED,
            examples="Q: 'What was revenue last month?' → Use net_revenue. Q: 'Monthly revenue trend' → Use net_revenue grouped by month.",
            notes="net_amount = total_amount - discount_amount - refund_amount + tax_amount. Only include completed orders.",
        ),
        BusinessDefinition(
            metric_name="gross_revenue",
            display_name="Gross Revenue (DEPRECATED)",
            definition="Total order value before discounts, refunds, and adjustments. This metric was previously used for revenue reporting but has been DEPRECATED since Q1 2025.",
            calculation="SUM(orders.total_amount)",
            source_table="business.orders",
            source_column="total_amount",
            filter_condition=None,
            owner="Finance Team",
            status=MetricStatus.DEPRECATED,
            examples="DO NOT use this for revenue reporting. It overstates revenue by ignoring discounts and refunds.",
            notes="Deprecated in favor of net_revenue. Still exists in the database for historical compatibility. If someone asks for 'revenue', use net_revenue instead.",
        ),
        BusinessDefinition(
            metric_name="recognized_revenue",
            display_name="Recognized Revenue (Experimental)",
            definition="Revenue recognized only when payment is confirmed complete. More conservative than net_revenue.",
            calculation="SUM(payments.amount) WHERE payments.status = 'completed'",
            source_table="business.payments",
            source_column="amount",
            filter_condition="status = 'completed'",
            owner="Finance Team",
            status=MetricStatus.EXPERIMENTAL,
            examples="Used in experimental cash-basis reporting. Not yet approved for official use.",
            notes="This is an experimental metric being tested by Finance. Do not use for official reporting yet.",
        ),
        BusinessDefinition(
            metric_name="active_customer_count",
            display_name="Active Customer Count",
            definition="Number of customers who are marked active AND have placed at least one order in the last 90 days. Simply being is_active=true is NOT sufficient.",
            calculation="COUNT(DISTINCT customers.id) WHERE customers.is_active = true AND customers.last_order_date >= CURRENT_DATE - INTERVAL '90 days'",
            source_table="business.customers",
            source_column="id",
            filter_condition="is_active = true AND last_order_date >= CURRENT_DATE - INTERVAL '90 days'",
            owner="Customer Success Team",
            status=MetricStatus.CERTIFIED,
            examples="Q: 'How many active customers?' → Use this definition, not just is_active flag.",
            notes="The is_active flag alone is unreliable - it's not always updated when customers churn. The 90-day order recency check ensures accuracy.",
        ),
        BusinessDefinition(
            metric_name="total_customer_count",
            display_name="Total Customer Count",
            definition="Count of all registered customers regardless of activity status.",
            calculation="COUNT(*) FROM customers",
            source_table="business.customers",
            source_column="id",
            filter_condition=None,
            owner="Customer Success Team",
            status=MetricStatus.CERTIFIED,
            examples="Q: 'How many customers do we have total?' → Use this.",
            notes="Includes active and inactive customers.",
        ),
        BusinessDefinition(
            metric_name="average_order_value",
            display_name="Average Order Value (AOV)",
            definition="Average net amount per completed order. Used for business performance tracking.",
            calculation="AVG(orders.net_amount) WHERE orders.status = 'completed'",
            source_table="business.orders",
            source_column="net_amount",
            filter_condition="status = 'completed'",
            owner="Finance Team",
            status=MetricStatus.CERTIFIED,
            examples="Q: 'What is our AOV?' → Average of net_amount for completed orders.",
            notes="Uses net_amount (not total_amount) to reflect actual revenue per order.",
        ),
        BusinessDefinition(
            metric_name="order_completion_rate",
            display_name="Order Completion Rate",
            definition="Percentage of orders that reach 'completed' status out of all non-pending orders.",
            calculation="COUNT(orders WHERE status='completed') / COUNT(orders WHERE status != 'pending') * 100",
            source_table="business.orders",
            source_column="status",
            filter_condition="status != 'pending'",
            owner="Operations Team",
            status=MetricStatus.CERTIFIED,
            examples="Q: 'What is our completion rate?' → Completed orders / (all orders - pending).",
            notes="Excludes pending orders since they haven't been processed yet.",
        ),
        BusinessDefinition(
            metric_name="refund_rate",
            display_name="Refund Rate",
            definition="Percentage of completed+refunded orders that ended in a refund.",
            calculation="COUNT(orders WHERE status='refunded') / COUNT(orders WHERE status IN ('completed','refunded')) * 100",
            source_table="business.orders",
            source_column="status",
            filter_condition="status IN ('completed', 'refunded')",
            owner="Finance Team",
            status=MetricStatus.CERTIFIED,
            examples="Q: 'What's our refund rate?' → Refunded / (Completed + Refunded).",
            notes="Only considers orders that were fulfilled (completed or refunded), not cancelled or pending.",
        ),
        BusinessDefinition(
            metric_name="monthly_recurring_revenue",
            display_name="Monthly Recurring Revenue (MRR)",
            definition="DRAFT metric. Not yet implemented properly as our billing is not subscription-based. Do not use.",
            calculation="Not defined",
            source_table="business.orders",
            source_column="net_amount",
            filter_condition=None,
            owner="Finance Team",
            status=MetricStatus.DRAFT,
            examples="This metric is not ready for use.",
            notes="We don't have subscription billing yet. This is a placeholder for future work.",
        ),
    ]
    for defn in definitions:
        session.add(defn)
    session.flush()


def seed_trust_signals(session) -> None:
    """Seed trust signals for assets."""
    signals = [
        TrustSignal(
            asset_name="net_revenue",
            trust_level=TrustLevel.CERTIFIED,
            reason="Approved by CFO as the official revenue metric for all reporting. Validated quarterly.",
            certified_by="Finance Team / CFO",
            last_validated=datetime(2026, 7, 1),
        ),
        TrustSignal(
            asset_name="gross_revenue",
            trust_level=TrustLevel.DEPRECATED,
            reason="Deprecated since Q1 2025. Overstates revenue by not accounting for discounts and refunds. Use net_revenue instead.",
            certified_by=None,
            last_validated=datetime(2025, 1, 15),
        ),
        TrustSignal(
            asset_name="recognized_revenue",
            trust_level=TrustLevel.EXPERIMENTAL,
            reason="Being tested as an alternative cash-basis revenue metric. Not approved for production reporting.",
            certified_by=None,
            last_validated=datetime(2026, 6, 1),
        ),
        TrustSignal(
            asset_name="active_customer_count",
            trust_level=TrustLevel.CERTIFIED,
            reason="Certified definition requiring both is_active flag AND 90-day order recency. Validated monthly.",
            certified_by="Customer Success Team",
            last_validated=datetime(2026, 7, 15),
        ),
        TrustSignal(
            asset_name="total_customer_count",
            trust_level=TrustLevel.CERTIFIED,
            reason="Simple count of all customers. Certified and reliable.",
            certified_by="Customer Success Team",
            last_validated=datetime(2026, 7, 15),
        ),
        TrustSignal(
            asset_name="average_order_value",
            trust_level=TrustLevel.CERTIFIED,
            reason="Certified AOV metric using net_amount for completed orders.",
            certified_by="Finance Team",
            last_validated=datetime(2026, 7, 1),
        ),
        TrustSignal(
            asset_name="orders",
            trust_level=TrustLevel.CERTIFIED,
            reason="Primary orders table. Contains multiple amount fields - always check business definitions before selecting a column.",
            certified_by="Data Engineering",
            last_validated=datetime(2026, 7, 1),
        ),
        TrustSignal(
            asset_name="customers",
            trust_level=TrustLevel.CERTIFIED,
            reason="Master customer table. Note: is_active flag may not always be current - validate with last_order_date.",
            certified_by="Data Engineering",
            last_validated=datetime(2026, 7, 1),
        ),
        TrustSignal(
            asset_name="products",
            trust_level=TrustLevel.CERTIFIED,
            reason="Product catalog. base_price is list price, actual order prices may vary.",
            certified_by="Product Team",
            last_validated=datetime(2026, 6, 15),
        ),
        TrustSignal(
            asset_name="payments",
            trust_level=TrustLevel.CERTIFIED,
            reason="Payment records. One payment per order. Reliable for payment analysis.",
            certified_by="Finance Team",
            last_validated=datetime(2026, 7, 1),
        ),
        TrustSignal(
            asset_name="monthly_recurring_revenue",
            trust_level=TrustLevel.STALE,
            reason="MRR metric is a draft placeholder. No subscription billing exists. Do not use.",
            certified_by=None,
            last_validated=None,
        ),
    ]
    for signal in signals:
        session.add(signal)
    session.flush()


def seed_schema_info(session) -> None:
    """Seed enriched schema descriptions for all columns."""
    schema_entries = [
        # customers table
        SchemaInfo(table_name="customers", column_name="id", data_type="integer", is_nullable=False, is_primary_key=True, description="Unique customer identifier", business_context="Auto-incrementing primary key"),
        SchemaInfo(table_name="customers", column_name="name", data_type="varchar(255)", is_nullable=False, is_primary_key=False, description="Customer full name", business_context="Used for display and communication"),
        SchemaInfo(table_name="customers", column_name="email", data_type="varchar(255)", is_nullable=False, is_primary_key=False, description="Customer email address (unique)", business_context="Primary contact method and login identifier"),
        SchemaInfo(table_name="customers", column_name="company", data_type="varchar(255)", is_nullable=True, is_primary_key=False, description="Company name if B2B customer", business_context="NULL for individual customers"),
        SchemaInfo(table_name="customers", column_name="segment", data_type="enum(enterprise,mid_market,smb,startup)", is_nullable=False, is_primary_key=False, description="Customer segment classification", business_context="Determines pricing tier and support level"),
        SchemaInfo(table_name="customers", column_name="is_active", data_type="boolean", is_nullable=False, is_primary_key=False, description="Whether customer account is active", business_context="WARNING: This flag alone does not define 'active customer'. Use the certified active_customer_count metric which also requires recent order activity."),
        SchemaInfo(table_name="customers", column_name="created_at", data_type="timestamp", is_nullable=False, is_primary_key=False, description="Account creation timestamp", business_context="Used for cohort analysis"),
        SchemaInfo(table_name="customers", column_name="last_order_date", data_type="date", is_nullable=True, is_primary_key=False, description="Date of most recent order", business_context="Used in active customer definition (must be within 90 days)"),
        # orders table
        SchemaInfo(table_name="orders", column_name="id", data_type="integer", is_nullable=False, is_primary_key=True, description="Unique order identifier", business_context="Auto-incrementing primary key"),
        SchemaInfo(table_name="orders", column_name="customer_id", data_type="integer", is_nullable=False, is_primary_key=False, description="Reference to customers.id", business_context="Foreign key to customers table"),
        SchemaInfo(table_name="orders", column_name="product_id", data_type="integer", is_nullable=False, is_primary_key=False, description="Reference to products.id", business_context="Foreign key to products table"),
        SchemaInfo(table_name="orders", column_name="order_date", data_type="date", is_nullable=False, is_primary_key=False, description="Date the order was placed", business_context="Use for time-based revenue queries"),
        SchemaInfo(table_name="orders", column_name="status", data_type="enum(pending,confirmed,completed,cancelled,refunded)", is_nullable=False, is_primary_key=False, description="Current order status", business_context="CRITICAL: Revenue metrics only count 'completed' orders. Cancelled and refunded orders should be excluded from revenue calculations."),
        SchemaInfo(table_name="orders", column_name="total_amount", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="Full order price before any adjustments", business_context="WARNING: This is NOT revenue. This is the raw price before discounts/refunds. Use net_amount for revenue. See gross_revenue (DEPRECATED) vs net_revenue (CERTIFIED)."),
        SchemaInfo(table_name="orders", column_name="discount_amount", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="Discount applied to the order", business_context="Subtracted from total_amount in net calculation"),
        SchemaInfo(table_name="orders", column_name="tax_amount", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="Tax (18% GST) charged on discounted amount", business_context="Added to revenue. Calculated as 18% of (total_amount - discount_amount)"),
        SchemaInfo(table_name="orders", column_name="refund_amount", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="Refund amount (non-zero only for refunded orders)", business_context="Only populated when status='refunded'. Full refund of the charged amount."),
        SchemaInfo(table_name="orders", column_name="net_amount", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="Final amount: total - discount - refund + tax", business_context="THIS IS THE CERTIFIED REVENUE COLUMN. Use this for all revenue queries with status='completed' filter."),
        # products table
        SchemaInfo(table_name="products", column_name="id", data_type="integer", is_nullable=False, is_primary_key=True, description="Unique product identifier", business_context="Auto-incrementing primary key"),
        SchemaInfo(table_name="products", column_name="name", data_type="varchar(255)", is_nullable=False, is_primary_key=False, description="Product name", business_context="Display name for the product"),
        SchemaInfo(table_name="products", column_name="category", data_type="varchar(100)", is_nullable=False, is_primary_key=False, description="Product category", business_context="Categories: Analytics, Security, Collaboration, Infrastructure, Data, AI/ML, Marketing"),
        SchemaInfo(table_name="products", column_name="base_price", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="List price of the product", business_context="Actual order amounts may differ based on customer segment and discounts"),
        SchemaInfo(table_name="products", column_name="is_active", data_type="boolean", is_nullable=False, is_primary_key=False, description="Whether product is currently offered", business_context="Inactive products can still appear in historical orders"),
        SchemaInfo(table_name="products", column_name="created_at", data_type="timestamp", is_nullable=False, is_primary_key=False, description="Product creation timestamp", business_context="When the product was added to catalog"),
        # payments table
        SchemaInfo(table_name="payments", column_name="id", data_type="integer", is_nullable=False, is_primary_key=True, description="Unique payment identifier", business_context="Auto-incrementing primary key"),
        SchemaInfo(table_name="payments", column_name="order_id", data_type="integer", is_nullable=False, is_primary_key=False, description="Reference to orders.id", business_context="Foreign key to orders table. One payment per order."),
        SchemaInfo(table_name="payments", column_name="amount", data_type="numeric(12,2)", is_nullable=False, is_primary_key=False, description="Payment amount", business_context="Should match order.net_amount for completed payments"),
        SchemaInfo(table_name="payments", column_name="method", data_type="enum(credit_card,debit_card,upi,net_banking,wallet)", is_nullable=False, is_primary_key=False, description="Payment method used", business_context="UPI is most common in India"),
        SchemaInfo(table_name="payments", column_name="status", data_type="enum(pending,completed,failed,refunded)", is_nullable=False, is_primary_key=False, description="Payment status", business_context="Only 'completed' payments represent actual money received"),
        SchemaInfo(table_name="payments", column_name="paid_at", data_type="timestamp", is_nullable=True, is_primary_key=False, description="When payment was completed", business_context="NULL for pending/failed payments"),
        SchemaInfo(table_name="payments", column_name="created_at", data_type="timestamp", is_nullable=False, is_primary_key=False, description="Payment record creation timestamp", business_context="When the payment attempt was initiated"),
    ]
    for entry in schema_entries:
        session.add(entry)
    session.flush()


def seed_lineage(session) -> None:
    """Seed data lineage relationships."""
    lineage_entries = [
        # Foreign key relationships
        Lineage(
            source_asset="customers",
            target_asset="orders",
            relationship_type="foreign_key",
            description="orders.customer_id references customers.id. Each order belongs to one customer.",
        ),
        Lineage(
            source_asset="products",
            target_asset="orders",
            relationship_type="foreign_key",
            description="orders.product_id references products.id. Each order is for one product.",
        ),
        Lineage(
            source_asset="orders",
            target_asset="payments",
            relationship_type="foreign_key",
            description="payments.order_id references orders.id. Each order has one payment record.",
        ),
        # Metric lineage
        Lineage(
            source_asset="orders.net_amount",
            target_asset="net_revenue",
            relationship_type="metric_source",
            description="net_revenue metric is calculated from orders.net_amount for completed orders.",
        ),
        Lineage(
            source_asset="orders.total_amount",
            target_asset="gross_revenue",
            relationship_type="metric_source",
            description="gross_revenue (DEPRECATED) was calculated from orders.total_amount.",
        ),
        Lineage(
            source_asset="payments.amount",
            target_asset="recognized_revenue",
            relationship_type="metric_source",
            description="recognized_revenue (EXPERIMENTAL) is calculated from payments.amount for completed payments.",
        ),
        Lineage(
            source_asset="customers",
            target_asset="active_customer_count",
            relationship_type="metric_source",
            description="active_customer_count is derived from customers table with is_active + last_order_date filters.",
        ),
        Lineage(
            source_asset="customers",
            target_asset="total_customer_count",
            relationship_type="metric_source",
            description="total_customer_count is COUNT(*) from customers table.",
        ),
        Lineage(
            source_asset="orders.net_amount",
            target_asset="average_order_value",
            relationship_type="metric_source",
            description="AOV is AVG(net_amount) for completed orders.",
        ),
    ]
    for entry in lineage_entries:
        session.add(entry)
    session.flush()


def seed_context_data():
    """Main function to seed all context layer data."""
    engine = get_engine(readonly=False)

    # Ensure schema exists
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS context"))
        conn.commit()

    # Create context tables
    Base.metadata.create_all(engine)

    session = get_session(readonly=False)
    try:
        # Check if already seeded
        existing = session.query(Asset).first()
        if existing:
            print("Context data already seeded. Skipping.")
            return

        print("Seeding assets...")
        seed_assets(session)

        print("Seeding business definitions...")
        seed_business_definitions(session)

        print("Seeding trust signals...")
        seed_trust_signals(session)

        print("Seeding schema info...")
        seed_schema_info(session)

        print("Seeding lineage...")
        seed_lineage(session)

        session.commit()
        print("\n✓ Context layer seeded successfully!")

    except Exception as e:
        session.rollback()
        print(f"Error seeding context: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_context_data()
