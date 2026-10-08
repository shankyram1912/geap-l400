---
name: analyze-tax-implications
description: Investigates property tax holding costs and assessment records for a parcel.
metadata:
  adk_additional_tools:
    - get_tax_assessment_data
---
# Analyze Tax Implications Skill

When investigating financial carrying costs or tax implications for a lot:
1. Locate the `parcel_apn` from the lot property records.
2. Use the `get_tax_assessment_data` tool with that APN to retrieve tax assessment details.
3. Note the annual tax amount and assessed valuations in your financial review.
