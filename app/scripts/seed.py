from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.agency import Agency, AgencyClient, AgencyMember
from app.models.analytics import CampaignMetric
from app.models.base import utcnow
from app.models.business import Business, BusinessMembership
from app.models.campaign import (
    Campaign,
    CampaignAudience,
    CampaignBudget,
    CampaignLocation,
    CampaignSchedule,
)
from app.models.inventory import AdInventory, PincodeInventory, PublisherPartner
from app.models.lead import Lead
from app.models.notification import Notification
from app.models.payment import Payment
from app.models.settings import SystemSetting
from app.models.user import Permission, Role, User
from app.services.pricing import calculate_budget

ROLES = [
    ("advertiser", "Advertiser account"),
    ("agency", "Agency account"),
    ("admin", "Platform administrator"),
    ("super_admin", "Super administrator"),
]

PERMISSIONS = {
    "advertiser": [
        "business:manage",
        "campaign:manage",
        "creative:manage",
        "payment:create",
        "analytics:view",
        "lead:manage",
    ],
    "agency": [
        "agency:manage",
        "client:manage",
        "campaign:manage",
        "analytics:view",
        "billing:manage",
    ],
    "admin": [
        "admin:access",
        "user:manage",
        "campaign:approve",
        "inventory:manage",
        "pricing:manage",
        "ai:configure",
    ],
    "super_admin": ["*"],
}

PINCODES = [
    ("682001", "Kochi", "Ernakulam", "Kerala", 42000, 18000, 240),
    ("682016", "Kochi", "Ernakulam", "Kerala", 38000, 16000, 245),
    ("682020", "Kochi", "Ernakulam", "Kerala", 35000, 15000, 250),
    ("682030", "Kochi", "Ernakulam", "Kerala", 41000, 17500, 255),
    ("560001", "Bengaluru", "Bengaluru Urban", "Karnataka", 52000, 25000, 280),
    ("560034", "Bengaluru", "Bengaluru Urban", "Karnataka", 48000, 22000, 275),
    ("600001", "Chennai", "Chennai", "Tamil Nadu", 45000, 20000, 260),
    ("600028", "Chennai", "Chennai", "Tamil Nadu", 39000, 17000, 255),
    ("110001", "New Delhi", "Central Delhi", "Delhi", 55000, 28000, 300),
    ("400001", "Mumbai", "Mumbai City", "Maharashtra", 60000, 30000, 320),
    ("500001", "Hyderabad", "Hyderabad", "Telangana", 47000, 21000, 270),
    ("695001", "Thiruvananthapuram", "Thiruvananthapuram", "Kerala", 33000, 14000, 230),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Role).count() > 0:
        return
    seed_all(db)


def seed_all(db: Session) -> None:
    roles: dict[str, Role] = {}
    for name, desc in ROLES:
        role = Role(name=name, description=desc, is_system=True)
        db.add(role)
        db.flush()
        roles[name] = role
        for code in PERMISSIONS[name]:
            db.add(Permission(role_id=role.id, code=code, description=code))

    settings = [
        ("minimum_daily_budget", "1000", "Minimum daily campaign budget in INR", "pricing"),
        ("media_margin_percent", "20", "Bada media margin percentage", "pricing"),
        ("default_cpm", "250", "Default estimated CPM in INR", "pricing"),
        ("tax_percent", "0", "Tax percentage applied on payable amount", "pricing"),
        ("supported_languages", "en,ml,ta,hi,te,kn", "Supported ad languages", "localization"),
    ]
    for key, value, desc, category in settings:
        db.add(SystemSetting(key=key, value=value, description=desc, category=category))

    for pin, city, district, state, households, reach, cpm in PINCODES:
        db.add(
            PincodeInventory(
                pincode=pin,
                city=city,
                district=district,
                state=state,
                estimated_households=households,
                estimated_ctv_reach=reach,
                avg_cpm=cpm,
                is_estimate=True,
                is_available=True,
            )
        )

    publisher = PublisherPartner(
        name="Demo CTV Network India",
        inventory_type="connected_tv",
        contact_email="partners@demo.bada.ai",
        status="demo",
        is_simulated=True,
        description="Simulated publisher inventory for development.",
        supported_languages="en,ml,ta,hi,te,kn",
        default_cpm=250,
    )
    db.add(publisher)
    db.flush()

    for pin, city, *_rest in PINCODES[:6]:
        db.add(
            AdInventory(
                publisher_id=str(publisher.id),
                name=f"Demo CTV — {city} {pin}",
                inventory_type="connected_tv",
                state=PINCODES[[p[0] for p in PINCODES].index(pin)][3],
                city=city,
                pincode=pin,
                language="ml" if city == "Kochi" else "en",
                available_impressions=random.randint(50000, 200000),
                cpm=250,
                is_available=True,
                is_simulated=True,
            )
        )

    admin = User(
        email="admin@bada.ai",
        password_hash=hash_password("Admin@12345"),
        full_name="Bada Admin",
        role_id=roles["admin"].id,
        is_active=True,
        is_verified=True,
        onboarding_completed=True,
        email_verified_at=utcnow(),
    )
    advertiser = User(
        email="advertiser@demo.bada.ai",
        password_hash=hash_password("Demo@12345"),
        full_name="Demo Advertiser",
        phone="+919876543210",
        role_id=roles["advertiser"].id,
        is_active=True,
        is_verified=True,
        onboarding_completed=True,
        email_verified_at=utcnow(),
    )
    agency_user = User(
        email="agency@demo.bada.ai",
        password_hash=hash_password("Demo@12345"),
        full_name="Demo Agency Owner",
        role_id=roles["agency"].id,
        is_active=True,
        is_verified=True,
        onboarding_completed=True,
        email_verified_at=utcnow(),
    )
    db.add_all([admin, advertiser, agency_user])
    db.flush()

    business = Business(
        owner_id=advertiser.id,
        name="Sree Krishna Jewellers",
        category="Jewellery",
        description="Family jewellery store in Kochi specializing in wedding collections.",
        website="https://example.com/skj",
        address="MG Road",
        city="Kochi",
        state="Kerala",
        pincode="682016",
        country="India",
        brand_tagline="Timeless craftsmanship for every celebration",
        brand_primary_color="#0B5FFF",
        brand_secondary_color="#0A1628",
        advertising_objective="increase_store_visits",
        target_languages="ml,en",
        onboarding_step=5,
        onboarding_completed=True,
        is_verified=True,
        status="active",
    )
    db.add(business)
    db.flush()
    db.add(BusinessMembership(business_id=business.id, user_id=advertiser.id, role="owner"))

    agency = Agency(
        owner_id=agency_user.id,
        name="Weft Media Agency",
        legal_name="Weft Media Pvt Ltd",
        email="agency@demo.bada.ai",
        status="active",
        description="Demo agency managing multiple local advertisers.",
    )
    db.add(agency)
    db.flush()
    db.add(AgencyMember(agency_id=agency.id, user_id=agency_user.id, role="owner"))
    db.add(AgencyClient(agency_id=agency.id, business_id=business.id))
    business.agency_id = agency.id

    campaign = Campaign(
        business_id=business.id,
        created_by=advertiser.id,
        name="Wedding Collection Launch — Kochi",
        objective="increase_store_visits",
        description="Promote wedding jewellery collection to Kochi neighbourhoods.",
        language="ml",
        status="active",
        video_duration=30,
        brief_text=(
            "I own a jewellery shop in Kochi. I want to promote our wedding collection "
            "and generate more store visits."
        ),
        is_simulated_delivery=True,
    )
    db.add(campaign)
    db.flush()

    db.add(
        CampaignAudience(
            campaign_id=campaign.id,
            demographics="Adults 25-54, household decision makers",
            interests="Jewellery, weddings, local shopping",
            languages="ml,en",
            age_min=25,
            age_max=54,
        )
    )
    for pin in ("682001", "682016", "682020", "682030"):
        pin_row = db.query(PincodeInventory).filter(PincodeInventory.pincode == pin).first()
        db.add(
            CampaignLocation(
                campaign_id=campaign.id,
                pincode=pin,
                city=pin_row.city if pin_row else "Kochi",
                state=pin_row.state if pin_row else "Kerala",
                district=pin_row.district if pin_row else "Ernakulam",
                estimated_audience=pin_row.estimated_ctv_reach if pin_row else 10000,
                is_estimate=True,
            )
        )

    breakdown = calculate_budget(db, daily_budget=2000, total_budget=30000, pincodes=["682016", "682030"])
    db.add(
        CampaignBudget(
            campaign_id=campaign.id,
            daily_budget=breakdown.daily_budget,
            total_budget=breakdown.total_budget,
            estimated_cpm=breakdown.estimated_cpm,
            estimated_impressions=breakdown.estimated_impressions,
            estimated_reach=breakdown.estimated_reach,
            media_spend=breakdown.media_spend,
            platform_fee=breakdown.platform_fee,
            tax_amount=breakdown.tax_amount,
            total_payable=breakdown.total_payable,
            is_estimate=True,
        )
    )
    db.add(
        CampaignSchedule(
            campaign_id=campaign.id,
            start_date=date.today() - timedelta(days=14),
            end_date=date.today() + timedelta(days=16),
            preferred_slots="prime_evening",
            prime_time=True,
            activated_at=utcnow(),
        )
    )

    db.add(
        Payment(
            user_id=advertiser.id,
            business_id=business.id,
            campaign_id=campaign.id,
            amount=breakdown.total_payable,
            currency="INR",
            status="paid",
            provider="mock",
            provider_order_id="mock_seed_order",
            provider_payment_id="mock_seed_pay",
            is_mock=True,
            receipt_number="RCPT-SEED01",
        )
    )

    # Simulated daily metrics
    for i in range(14):
        d = date.today() - timedelta(days=13 - i)
        impressions = random.randint(800, 1600)
        db.add(
            CampaignMetric(
                campaign_id=campaign.id,
                metric_date=d,
                impressions=impressions,
                estimated_reach=int(impressions * 0.65),
                completed_views=int(impressions * 0.72),
                qr_scans=random.randint(3, 12),
                website_visits=random.randint(5, 18),
                whatsapp_inquiries=random.randint(2, 8),
                phone_calls=random.randint(1, 5),
                leads=random.randint(2, 7),
                spend=round(random.uniform(1800, 2200), 2),
                is_simulated=True,
            )
        )

    lead_samples = [
        ("Ananya Nair", "9876500001", "qr", "682030", "Interested in bridal set"),
        ("Rahul Menon", "9876500002", "whatsapp", "682016", "Wedding collection enquiry"),
        ("Fatima Beevi", "9876500003", "phone", "682001", "Store visit timing"),
        ("Vivek Krishnan", "9876500004", "website", "682020", "Gold rate offer"),
        ("Meera Thomas", "9876500005", "qr", "682030", "Scan from TV ad"),
    ]
    for name, phone, source, pin, inquiry in lead_samples:
        db.add(
            Lead(
                business_id=business.id,
                campaign_id=campaign.id,
                name=name,
                phone=phone,
                inquiry=inquiry,
                source=source,
                pincode=pin,
                status="new" if source == "qr" else "contacted",
            )
        )

    db.add(
        Notification(
            user_id=advertiser.id,
            title="Welcome to Bada",
            message="Your demo account is ready. Explore campaigns, AI Studio, and analytics.",
            type="welcome",
        )
    )
    db.add(
        Notification(
            user_id=advertiser.id,
            title="Campaign activated",
            message="Wedding Collection Launch — Kochi is active (simulated delivery).",
            type="campaign_activated",
            entity_type="campaign",
            entity_id=str(campaign.id),
        )
    )

    db.commit()
    print("Seed data created successfully.")
    seed_omnichannel_demo(db)


def seed_omnichannel_demo(db: Session) -> None:
    """Idempotent seed for channel catalog + sample local inventory."""
    from app.models.channels import LocalAdProvider, LocalInventoryListing
    from app.services.channel_service import ensure_channel_catalog

    ensure_channel_catalog(db)
    if db.query(LocalAdProvider).count() > 0:
        return

    provider = LocalAdProvider(
        business_name="Kochi Screen Network",
        contact_name="Local Ops",
        contact_email="screens@demo.bada.ai",
        contact_phone="+919876543299",
        description="Demo local LED and mall screen inventory owner.",
        status="active",
    )
    db.add(provider)
    db.flush()
    listings = [
        {
            "title": "Lulu Mall LED — Entrance",
            "inventory_type": "mall_screen",
            "address": "Lulu Mall, Edappally",
            "city": "Kochi",
            "district": "Ernakulam",
            "state": "Kerala",
            "pincode": "682024",
            "screen_size": "10ft",
            "resolution": "1920x1080",
            "formats": "led_loop,video_10s",
            "operating_hours": "10:00-22:00",
            "price": 2500,
            "estimated_impressions": 45000,
            "language": "ml",
        },
        {
            "title": "MG Road Retail Screen",
            "inventory_type": "retail_screen",
            "address": "MG Road",
            "city": "Kochi",
            "district": "Ernakulam",
            "state": "Kerala",
            "pincode": "682016",
            "screen_size": "55in",
            "resolution": "1920x1080",
            "formats": "retail_screen,qr_cta",
            "operating_hours": "09:00-21:00",
            "price": 1200,
            "estimated_impressions": 18000,
            "language": "ml",
        },
        {
            "title": "Edappally Junction LED Board",
            "inventory_type": "led_outdoor",
            "address": "Edappally Junction",
            "city": "Kochi",
            "district": "Ernakulam",
            "state": "Kerala",
            "pincode": "682024",
            "screen_size": "20ft",
            "resolution": "3840x2160",
            "formats": "billboard_digital",
            "operating_hours": "06:00-23:00",
            "price": 5000,
            "estimated_impressions": 90000,
            "language": "ml,en",
        },
    ]
    for item in listings:
        db.add(
            LocalInventoryListing(
                provider_id=provider.id,
                status="approved",
                is_estimate=True,
                pricing_model="cpm_slot",
                **item,
            )
        )
    db.commit()
    print("Omnichannel demo inventory seeded.")


if __name__ == "__main__":
    from app.core.database import Base, SessionLocal, engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        seed_all(session)
    finally:
        session.close()
