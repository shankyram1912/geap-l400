---
name: analyze-opportunity
description: Investigates a land parcel for real estate investment opportunity analysis.
metadata:
  adk_additional_tools:
    - get_lot_data
---
# Analyze Opportunity Skill

When asked to investigate a property or analyze an investment opportunity for a lot:
1. Use the `get_lot_data` tool to lookup the property attributes by its lot ID.
2. Review the basic details returned, such as acreage, zoning, and last sale price.
3. Consult the `analyze-flood-risk` skill to investigate any environmental or flood zone classifications for the lot.
4. Consult the `analyze-tax-implications` skill to investigate property tax holding costs and assessment records using the lot's parcel APN.
5. Note any obvious physical or financial characteristics of the land parcel based on your findings across all three investigation skills.
