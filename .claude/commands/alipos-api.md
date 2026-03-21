AliPOS restaurant POS integration API reference. Use when integrating with AliPOS, creating orders, fetching menus, building Telegram bots or third-party apps that place food orders, or working with alipos.uz.

Read the full skill and reference files for complete details:
- Skill overview: .github/skills/alipos-api/SKILL.md
- Full API reference: .github/skills/alipos-api/references/api-reference.md

## Base URL
```
https://web.alipos.uz
```

## Authentication
OAuth 2.0 Client Credentials → `POST /security/oauth/token` → Bearer token (24h).

## Key Endpoints
| Endpoint | Method | Purpose |
|---|---|---|
| `/security/oauth/token` | POST | Get Bearer token |
| `/restaurants` | GET | List partner restaurants |
| `/api/Integration/v1/menu/{restaurantId}/composition` | GET | Full menu |
| `/api/Integration/v1/order` | POST | Create order |
| `/api/Integration/v1/order/{orderId}` | DELETE | Cancel order |
| `/api/Integration/v1/paymentMethod/all` | GET | Payment methods |

## Order Types
`delivery` | `pickup` | `marketplace` | `inplace` (requires `tableId`)

## Order Statuses
`NEW` → `ACCEPTED_BY_RESTAURANT` → `READY` → `TAKEN_BY_COURIER` | `CANCELED`

$ARGUMENTS
