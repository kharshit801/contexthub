"""Unified seed script - seeds both business data and context layer.

Usage:
    python -m app.db.seed       # Seeds business data
    python seed.py              # Seeds everything (business + context)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.seed import seed_business_data
from app.context.seed import seed_context_data


def main():
    """Seed all data."""
    print("=" * 50)
    print("  ContextHub - Database Seeding")
    print("=" * 50)

    print("\n[1/2] Seeding business data...")
    seed_business_data()

    print("\n[2/2] Seeding context layer...")
    seed_context_data()

    print("\n" + "=" * 50)
    print("  ✓ All data seeded successfully!")
    print("=" * 50)
    print("\nYou can now run:")
    print("  python cli.py                    # Interactive mode")
    print("  python cli.py --compare          # Compare both agents")
    print("  python -m evaluation.runner      # Run evaluation")
    print("  uvicorn app.main:app --reload    # Start API server")


if __name__ == "__main__":
    main()
