-- Add richer plan metadata so API responses can be driven entirely from DB.

ALTER TABLE plans ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE plans ADD COLUMN price TEXT NOT NULL DEFAULT '';
ALTER TABLE plans ADD COLUMN button_text TEXT NOT NULL DEFAULT 'Get started';
ALTER TABLE plans ADD COLUMN features TEXT NOT NULL DEFAULT '[]';
ALTER TABLE plans ADD COLUMN is_popular INTEGER NOT NULL DEFAULT 0;
ALTER TABLE plans ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;

UPDATE plans
SET
    description = CASE name
        WHEN 'tier_1' THEN 'For individuals getting started with one repository workspace.'
        WHEN 'tier_2' THEN 'For growing teams that need AI and collaboration features.'
        WHEN 'tier_3' THEN 'For larger organizations managing many repositories and members.'
        ELSE description
    END,
    price = CASE name
        WHEN 'tier_1' THEN 'Free'
        WHEN 'tier_2' THEN '999/month'
        WHEN 'tier_3' THEN 'Custom'
        ELSE price
    END,
    button_text = CASE name
        WHEN 'tier_1' THEN 'Get started'
        WHEN 'tier_2' THEN 'Start free trial'
        WHEN 'tier_3' THEN 'Contact sales'
        ELSE button_text
    END,
    features = CASE name
        WHEN 'tier_1' THEN '["1 repository","1 member","Basic repository access"]'
        WHEN 'tier_2' THEN '["5 repositories","5 members","AI Q&A","Team collaboration"]'
        WHEN 'tier_3' THEN '["Unlimited repositories","Unlimited members","AI Q&A","Multi-repo insights"]'
        ELSE features
    END,
    is_popular = CASE name
        WHEN 'tier_2' THEN 1
        ELSE 0
    END,
    sort_order = CASE name
        WHEN 'tier_1' THEN 1
        WHEN 'tier_2' THEN 2
        WHEN 'tier_3' THEN 3
        ELSE sort_order
    END
WHERE name IN ('tier_1', 'tier_2', 'tier_3');
