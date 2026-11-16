# Where the item prices came from

Collected 16 Nov 2026. Prices change, so update the CSVs whenever you like: one row per
currency, `currency_code,local_price,date`. A country with no row is simply left out.

## iphone.csv: iPhone 17, 256 GB
- Apple's own store prices as listed by https://iphonepricesworldwide.com/products/apple/iphone-17
  and https://opentherank.com/apple-pricing/iphone-17/ (the two agreed on every country).
- The US price is **before sales tax**; every other country's price includes VAT/GST.
  That makes the US look a little cheaper than a true like-for-like comparison.
- No price was listed for South Africa, Indonesia or Colombia, so they're left out.

## netflix.csv: Netflix Standard plan, per month
- https://geonode.com/blog/netflix-prices-by-country (collected 7 Oct 2026).
- Chile and Colombia from https://www.netflixindex.com/ (Oct 2026), which disagreed with
  Geonode on Brazil (R$51.90 vs R$44.90); we used Geonode's R$44.90.
- Netflix isn't available in China; no Indonesia price was found.

## gasoline.csv: 1 liter of regular (95-octane) gasoline
- Country pages on https://www.globalpetrolprices.com (each row's date is that page's date;
  some are several months old).
- US: $4.315 per gallon (dailyfuels.com, November 2026) ÷ 3.785 liters per gallon = $1.14 per liter.
