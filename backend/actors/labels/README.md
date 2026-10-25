# Independent Fashion Labels

Find **verified independent fashion labels** and their **in-stock products** from just a brand name or website.

Search engines and shopping feeds favor big retailers, so small labels often show up only as resale listings. This
actor goes to each label's own store instead.

## What it does

1. **Finds the store.** A website is used as given. For a name like "Batul The Collection" it tries the domains small
   labels usually use (batulthecollection.com, batul.com, shopbatul.com, batulthelabel.com...). It keeps a guess only
   if the store calls itself by that name, so a stranger who owns the domain isn't matched.
2. **Verifies it's independent.** Every brand gets five checks, all from the store's public catalog:

   | Check | Passes when |
   |---|---|
   | `real_store` | it sells something with a price, in stock |
   | `independent` | it isn't a marketplace, chain or big retailer |
   | `own_label` | it is one label's store, not a boutique reselling many brands (fewer than 10 vendors, or one vendor with most products) |
   | `small` | it has fewer than 1,000 products |
   | `established` | it has been selling for over six months (drop-shipping stores rarely have) |

3. **Returns products**, optionally matched to what you're looking for ("satin slip skirt"). A named item type only
   matches that type, and a colour alone never counts as a match.

It reads only public `/products.json` and `/meta.json` endpoints: no logins, no third-party scrapers, no personal data.
It works for stores on Shopify, which most small labels use.

## Input

```json
{"brands": ["Batul The Collection", "velascarves.com"], "query": "slip skirt", "maxPrice": 250,
 "itemsPerBrand": 10, "verifiedOnly": true}
```

## Output

Each dataset item is one product: `title, url, price, currency, image_urls, sizes, brand, retailer, available,
description`, plus `domain`, `verified` and `checks` for the label it came from. The `OUTPUT` record lists every
brand you asked for, with the store it resolved to (or why none was found) and the result of each check.

## Use it for

- **Shopping agents** that should show small labels new, not only as resale listings.
- **Brand research**: check whether a label is a real, independent, established store before you feature or stock it.
- **Watching a few labels' new arrivals**: schedule a run with a `query` and compare datasets.

## Example result

From a live run on 2026-10-24 with `["Batul The Collection", "Veiled", "Vela"]`:

| Brand | Resolved store | Verified |
|---|---|---|
| Batul The Collection | batulthecollection.com | yes |
| Veiled | veiled.com | yes |
| Vela | no store found by name (vela.com is a software company) | no; pass `velascarves.com` instead |

## Limits

- Only finds stores on **Shopify**. A label on Squarespace, Wix or its own platform comes back as "no store found".
- A name lookup tries common domain patterns. A label with an unusual domain needs its website passed in.
- The checks use the public catalog only, so they can't see who owns a store. `independent` means "not a known
  marketplace, chain or big retailer", nothing more.
- Prices are in each shop's own currency; `maxPrice` is compared in that currency.

## Cost

No third-party scrapers and no per-result fee: you pay only the run's compute. A run over a handful of labels
finishes in seconds.

Built for [Niche](https://github.com/arissazheng/niche), a shopping assistant that finds pieces for your taste.
