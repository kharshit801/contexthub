"""Seed the business database with realistic enterprise data."""

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.db.connection import Base, get_engine, get_session
from app.db.models import (
    Customer,
    CustomerSegment,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
)

random.seed(42)  # Reproducible data

# Product catalog
PRODUCTS = [
    # Analytics
    ("DataViz Pro", "Analytics", 15000),
    ("InsightEngine", "Analytics", 45000),
    ("MetricsDashboard", "Analytics", 8000),
    ("PredictiveAI Suite", "Analytics", 120000),
    ("ReportBuilder", "Analytics", 5000),
    # Security
    ("SecureVault", "Security", 25000),
    ("ThreatShield Pro", "Security", 85000),
    ("ComplianceManager", "Security", 55000),
    ("IdentityGuard", "Security", 35000),
    ("AuditTrail", "Security", 18000),
    # Collaboration
    ("TeamSync", "Collaboration", 3000),
    ("ProjectFlow", "Collaboration", 12000),
    ("DocHub Enterprise", "Collaboration", 8000),
    ("ChatOps Platform", "Collaboration", 6000),
    ("MeetingAI", "Collaboration", 4500),
    # Infrastructure
    ("CloudScale", "Infrastructure", 200000),
    ("ContainerOrch Pro", "Infrastructure", 150000),
    ("MonitorStack", "Infrastructure", 40000),
    ("LogAnalyzer", "Infrastructure", 22000),
    ("CICDPipeline", "Infrastructure", 30000),
    # Data
    ("DataWarehouse Pro", "Data", 180000),
    ("ETL Automator", "Data", 65000),
    ("DataQuality Suite", "Data", 45000),
    ("CatalogManager", "Data", 55000),
    ("StreamProcessor", "Data", 90000),
    # AI/ML
    ("MLOps Platform", "AI/ML", 250000),
    ("ModelServing Pro", "AI/ML", 130000),
    ("FeatureStore", "AI/ML", 75000),
    ("ExperimentTracker", "AI/ML", 35000),
    ("AutoML Suite", "AI/ML", 180000),
    # Marketing
    ("CampaignManager", "Marketing", 28000),
    ("EmailAutomation", "Marketing", 15000),
    ("SEO Toolkit", "Marketing", 10000),
    ("SocialAnalytics", "Marketing", 12000),
    ("AdOptimizer", "Marketing", 35000),
]

INDIAN_FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Reyansh", "Sai", "Arnav",
    "Dhruv", "Kabir", "Ananya", "Diya", "Saanvi", "Isha", "Kiara", "Riya",
    "Priya", "Neha", "Pooja", "Shreya", "Rahul", "Amit", "Rohan", "Vikram",
    "Suresh", "Rajesh", "Kiran", "Meera", "Lakshmi", "Kavya", "Harsh", "Deepak",
    "Nikhil", "Sanjay", "Manoj", "Sneha", "Divya", "Anjali", "Nisha", "Tanvi",
]

INDIAN_LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Kumar", "Singh", "Gupta", "Reddy", "Nair",
    "Joshi", "Mehta", "Shah", "Iyer", "Pillai", "Rao", "Desai", "Kapoor",
    "Malhotra", "Bhat", "Menon", "Chatterjee", "Banerjee", "Das", "Mukherjee",
    "Agarwal", "Tiwari", "Pandey", "Mishra", "Saxena", "Chauhan", "Yadav",
]

COMPANIES = [
    "TechNova Solutions", "DataMind Analytics", "CloudFirst India", "InnovateTech",
    "DigitalEdge Systems", "Infosync Labs", "NextGen Software", "CoreStack Tech",
    "Velocity Computing", "PrimeLogic", "AlphaWave Tech", "BrightPath Digital",
    "CyberNest Security", "DeepTech AI", "EagleEye Analytics", "FlexiCloud",
    "GrowthStack", "HyperScale India", "IntelliSoft", "JetStream Data",
    "KernelTech", "LuminAI", "MegaByte Systems", "NeuralPath", "OmniTech Solutions",
    "PulseTech", "QuantumLeap AI", "RapidOps", "SilverLine Tech", "TurboStack",
    None, None, None, None, None,  # Some customers without company (individual)
]


def create_products(session) -> list[Product]:
    """Create product catalog."""
    products = []
    for name, category, price in PRODUCTS:
        product = Product(
            name=name,
            category=category,
            base_price=Decimal(str(price)),
            is_active=random.random() > 0.1,  # 90% active
        )
        session.add(product)
        products.append(product)
    session.flush()
    return products


def create_customers(session) -> list[Customer]:
    """Create realistic customer base."""
    customers = []
    segments = list(CustomerSegment)
    segment_weights = [0.1, 0.25, 0.4, 0.25]  # enterprise, mid_market, smb, startup

    for i in range(1000):
        first = random.choice(INDIAN_FIRST_NAMES)
        last = random.choice(INDIAN_LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{i}@{'gmail.com' if random.random() > 0.5 else 'company.co.in'}"
        company = random.choice(COMPANIES)
        segment = random.choices(segments, weights=segment_weights, k=1)[0]

        # ~80% active, ~20% inactive
        is_active = random.random() > 0.2

        created_at = datetime(2023, 1, 1) + timedelta(days=random.randint(0, 900))

        customer = Customer(
            name=name,
            email=email,
            company=company,
            segment=segment,
            is_active=is_active,
            created_at=created_at,
        )
        session.add(customer)
        customers.append(customer)
    session.flush()
    return customers


def create_orders(session, customers: list[Customer], products: list[Product]) -> list[Order]:
    """Create orders with realistic distributions and ambiguous amounts."""
    orders = []
    statuses = list(OrderStatus)
    status_weights = [0.05, 0.15, 0.60, 0.15, 0.05]  # pending, confirmed, completed, cancelled, refunded

    start_date = date(2024, 1, 1)
    end_date = date(2026, 8, 15)
    date_range = (end_date - start_date).days

    for i in range(5000):
        customer = random.choice(customers)
        product = random.choice(products)
        order_date = start_date + timedelta(days=random.randint(0, date_range))

        # Bias more orders toward July 2026 for demo
        if random.random() < 0.08:
            order_date = date(2026, 7, 1) + timedelta(days=random.randint(0, 30))

        status = random.choices(statuses, weights=status_weights, k=1)[0]

        # Calculate amounts
        # Enterprise customers get higher amounts
        multiplier = {
            CustomerSegment.ENTERPRISE: random.uniform(2.0, 5.0),
            CustomerSegment.MID_MARKET: random.uniform(1.0, 3.0),
            CustomerSegment.SMB: random.uniform(0.5, 1.5),
            CustomerSegment.STARTUP: random.uniform(0.3, 1.0),
        }[customer.segment]

        total_amount = Decimal(str(round(float(product.base_price) * multiplier, 2)))

        # Discount on ~30% of orders
        discount_amount = Decimal("0")
        if random.random() < 0.3:
            discount_pct = random.uniform(0.05, 0.25)
            discount_amount = Decimal(str(round(float(total_amount) * discount_pct, 2)))

        # Tax (18% GST)
        tax_amount = Decimal(str(round(float(total_amount - discount_amount) * 0.18, 2)))

        # Refund only for refunded orders
        refund_amount = Decimal("0")
        if status == OrderStatus.REFUNDED:
            refund_amount = total_amount - discount_amount + tax_amount  # Full refund

        # net_amount = total - discount - refund + tax
        net_amount = total_amount - discount_amount - refund_amount + tax_amount

        order = Order(
            customer_id=customer.id,
            product_id=product.id,
            order_date=order_date,
            status=status,
            total_amount=total_amount,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            refund_amount=refund_amount,
            net_amount=net_amount,
        )
        session.add(order)
        orders.append(order)

    session.flush()
    return orders


def create_payments(session, orders: list[Order]) -> list[Payment]:
    """Create payments linked to orders."""
    methods = list(PaymentMethod)
    payments = []

    for order in orders:
        method = random.choice(methods)

        if order.status == OrderStatus.COMPLETED:
            payment_status = PaymentStatus.COMPLETED
            paid_at = datetime.combine(order.order_date, datetime.min.time()) + timedelta(hours=random.randint(0, 48))
        elif order.status == OrderStatus.CONFIRMED:
            payment_status = PaymentStatus.COMPLETED
            paid_at = datetime.combine(order.order_date, datetime.min.time()) + timedelta(hours=random.randint(0, 24))
        elif order.status == OrderStatus.CANCELLED:
            payment_status = random.choice([PaymentStatus.FAILED, PaymentStatus.REFUNDED])
            paid_at = None
        elif order.status == OrderStatus.REFUNDED:
            payment_status = PaymentStatus.REFUNDED
            paid_at = datetime.combine(order.order_date, datetime.min.time()) + timedelta(hours=random.randint(0, 24))
        else:  # PENDING
            payment_status = PaymentStatus.PENDING
            paid_at = None

        amount = order.net_amount if order.status != OrderStatus.REFUNDED else order.total_amount - order.discount_amount + order.tax_amount

        payment = Payment(
            order_id=order.id,
            amount=amount,
            method=method,
            status=payment_status,
            paid_at=paid_at,
        )
        session.add(payment)
        payments.append(payment)

    session.flush()
    return payments


def update_customer_last_order_dates(session, customers: list[Customer], orders: list[Order]):
    """Update last_order_date for each customer."""
    customer_last_orders: dict[int, date] = {}
    for order in orders:
        cid = order.customer_id
        if cid not in customer_last_orders or order.order_date > customer_last_orders[cid]:
            customer_last_orders[cid] = order.order_date

    for customer in customers:
        if customer.id in customer_last_orders:
            customer.last_order_date = customer_last_orders[customer.id]


def seed_business_data():
    """Main seed function for business data."""
    engine = get_engine(readonly=False)

    # Create schemas if not exist
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS business"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS context"))
        conn.commit()

    # Create tables
    Base.metadata.create_all(engine)

    session = get_session(readonly=False)
    try:
        # Check if data already exists
        existing = session.query(Customer).first()
        if existing:
            print("Business data already seeded. Skipping.")
            return

        print("Seeding products...")
        products = create_products(session)
        print(f"  Created {len(products)} products")

        print("Seeding customers...")
        customers = create_customers(session)
        print(f"  Created {len(customers)} customers")

        print("Seeding orders...")
        orders = create_orders(session, customers, products)
        print(f"  Created {len(orders)} orders")

        print("Seeding payments...")
        payments = create_payments(session, orders)
        print(f"  Created {len(payments)} payments")

        print("Updating customer last order dates...")
        update_customer_last_order_dates(session, customers, orders)

        session.commit()
        print("\n✓ Business data seeded successfully!")
        print(f"  Products: {len(products)}")
        print(f"  Customers: {len(customers)}")
        print(f"  Orders: {len(orders)}")
        print(f"  Payments: {len(payments)}")

    except Exception as e:
        session.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_business_data()
