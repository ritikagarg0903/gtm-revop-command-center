"""Company context for the sample dataset; never enriches real records with invented facts."""
import hashlib

PROFILE_FIELDS = ['industry', 'company_description', 'target_customers', 'business_model', 'headquarters', 'profile_source']
PROFILES = [
    ('B2B software', 'Builds workflow software for revenue and operations teams.', 'Mid-sized B2B companies', 'Annual software subscriptions'),
    ('Logistics', 'Coordinates freight delivery and shipment visibility for businesses.', 'Retailers and manufacturers', 'Contract-based logistics services'),
    ('Professional services', 'Provides implementation and operations consulting.', 'Growing enterprise teams', 'Project fees and retainers'),
    ('E-commerce technology', 'Provides tools for merchants to manage online sales and fulfillment.', 'Online retailers and consumer brands', 'Subscriptions and usage-based fees'),
    ('Industrial technology', 'Builds monitoring tools for industrial equipment and maintenance teams.', 'Manufacturers and industrial operators', 'Software subscriptions and implementation services'),
]


def add_sample_company_context(records):
    records = records.copy()
    for index, row in records.iterrows():
        seed = int(hashlib.sha256(str(row.canonical_domain).encode()).hexdigest()[:8], 16)
        industry, description, customers, model = PROFILES[seed % len(PROFILES)]
        values = dict(industry=industry, company_description=description, target_customers=customers,
                      business_model=model, headquarters={'West': 'San Francisco, USA', 'Central': 'Chicago, USA',
                      'East': 'Boston, USA', 'International': 'London, UK'}[row.territory],
                      profile_source='Synthetic company profile')
        for field, value in values.items():
            records.loc[index, field] = value
    return records


def company_context(records):
    """Missing provider fields stay explicitly unknown; derive outreach guidance from recorded signals."""
    result = records.copy()
    for field in PROFILE_FIELDS:
        if field not in result:
            result[field] = 'Not provided'
        result[field] = result[field].fillna('Not provided')
    def angle(row):
        if row.pricing_page_views_30d > 0:
            return 'Offer a short fit-and-pricing conversation; ask what they are evaluating.'
        if row.content_engagements_30d > 0:
            return 'Share a relevant use case and ask which workflow they want to improve.'
        return 'Start with a role-specific discovery question; confirm priorities before pitching.'
    result['suggested_outreach'] = result.apply(angle, axis=1) if len(result) else []
    result['engagement_summary'] = result.apply(lambda r: f'{r.website_visits_30d} site visits, {r.content_engagements_30d} content interactions, {r.pricing_page_views_30d} pricing-page views in 30 days', axis=1) if len(result) else []
    return result
