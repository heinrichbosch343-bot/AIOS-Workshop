# Harties Board: directory, search, food specials and events (research run, 5 Nov 2026)

Written for Heinrich. Everything below is built into the app locally (branch `directory` in the app folder) and **not shipped**. The live site is unchanged.

## What was done

| Part | Result |
|---|---|
| Local businesses | 1,705 places from Google Maps (two sweeps: 485 + 1,157 searches, only about 1% of the second sweep was new, so coverage of what Maps lists is close to complete). Seven reviewers read every row. **1,499 kept**, about 200 dropped (outside Harties, houses, duplicates, B2B, adult). |
| Categories | Two new groups, **Stay & visit** and **Community & help**, plus 25 new sub-groups (pharmacies, schools, pre-schools, accountants, lawyers, security, garages, clothing, furniture and more). 14 groups in all. |
| Search | Rebuilt. Finds **what people call it**, not only what the listing says (plumber finds geyser and drain people), forgives typing slips ("dentits") only when nothing matches exactly, ignores filler ("who can fix my geyser"), keeps phrases together ("bottle store"), ranks the right group first, and can be narrowed to one group. Popular searches show on an empty search page. |
| Food specials and weekly nights | Every food place's own website was read (106 sites, 3 helpers). **62 specials and nights at 17 places** (V8 Roadhouse, Hennie's, Mozambik, Belize, Panarottis, Welwitschia market and others). Cards show "Tue · Pasta night" lines; the Food page has **All / Specials / Events** on the weekly view. |
| Events, next 6 months | 5 helpers plus the WhatsApp group: 139 records, 106 after merging duplicates. **78 on the board**, 12 held back for a check or your decision, 27 on a watch list (real events, no date yet). A new **Coming up** page lists the dated ones for six months; weekly things stay under This week. Report: `outputs/community-app/events/events-report.md`. |
| Help numbers | 43 verified numbers, each read from an official page, with its link and the date checked (police, NSRI Hartbeespoort, ambulances, Madibeng, Eskom, estates, helplines). Emergency numbers like 112 and 10111 get a Call button. |

## What the people will see

- **Browse** now shows 14 groups. Food has 207 places, Home & trades 263, Stay & visit 218, Shops 179, Business 150, Beauty 135, Health 80, Community & help 104, Events 74, Kids & schools 67, Sport 60.
- Every imported place says plainly: *Listed from public information, not by the business. Call first. Is this your business? List it yourself, or tell us to fix or remove it.* They sort **neighbour-recommended first, then by how busy and well rated the place is on public maps** (never shown, only used to order). "A to Z" is one tap away.
- Lists load 30 at a time with "Show more".
- Events that are not certain carry a note on the card ("Date from a listing, check with the organiser" or "Date to be confirmed"). The page links to the organiser's own page.
- The app now looks six months ahead (it was four). Before this, a race in March showed as "finished".

## Events on the board, by month

Nov 2026: 33 (Braai Festival 14-15 Nov, Black Horse Christmas Market 29 Nov, Conquer the Trails 29 Nov, Gospel Festival, HAUS, retreats). Dec: 19 (Boathouse Affair at Pecanwood 5 Dec, Best Dam Trail 5 Dec, Padel Park Wellness Day 5 Dec, Christmas Day buffets and cruise). Jan-Apr 2027: 17 (monthly lectures, The Grind 6 Feb, **TROJAN Om Die Dam Sat 20 Mar 2027, confirmed by the organiser's own page**). Weekly (8): Welwitschia market, Sunday market at Laurentina, Padel Americano Thursdays, karaoke Fridays, Friday happy hour.

## What I could not find (be honest with people about this)

- **No New Year's Eve 2026/27 party, no Easter 2027, no carols, no Santa photos, no Black Friday event, nothing after late April.** Organisers have not posted yet. Re-run in late November.
- **Pecanwood and Islands estate clubs publish no events** on the web. Their events live on Facebook and WhatsApp, which cannot be read. The Beacon of Hope tree lighting and the Village Mall night market happened in 2025 but have no 2026 date yet (watch list).
- No tennis or golf club events at Pecanwood, no fishing or sailing regattas, no municipal events calendar. Most Pecanwood College, church and estate news is Facebook-only.
- **Food specials are thin on websites**: 62 across 106 sites. Most restaurants post specials on Facebook only. The honest fix is to let restaurants post their own (the Post tab already does this) and to ask the top 20 for a flyer.
- Opening hours only exist for about a third of the places; Google only gave days for some.

## Held back on purpose (12 events)

Anything where the researcher flagged a conflict or low confidence is **not** on the board until someone checks it: ROD Reggae & Comedy (header says 24 Apr 2027, text says 26 Sep 2026), Down Base and Grateful Fest (only a map pin for the venue), the Wellness Day (dates conflict, may not be in Harties), the Tin Roof Christmas buffet and Armistice service (old snippets), Valley of Wonders Market (a 2024 blog) and Luxliner Route 66 (weekday conflict). The **hookah meeting on 26 Dec** is left for your decision (adult social event with a first name as the organiser).

## Things to decide before shipping

1. **Rights and privacy.** The 1,499 listings come from public Google Maps listings, with phone numbers, as published. Many are sole traders. They are marked "from public information" with a fix or remove link, but POPIA section 69 (direct marketing) and the "responsible party" line are still open from the privacy review. Recommend: ship, answer every removal request within a day.
2. **Food specials that are brand-wide.** Hennie's, Mozambik and Panarottis specials come from their own pages; **Del Forno's come from the national page and the card says to confirm with the store.** Say if you would rather leave Del Forno out.
3. **Ship order.** The other Claude tab's work (accounts, owner editing, Sponsored row) is separate. Whoever ships second merges the other's code first. Nothing here changes how a business edits its listing.
4. Photos: imported listings have no pictures (a coloured band with the group icon). Asking the top 30 businesses for a photo would lift the pages the most.

## How to refresh it

`python scripts/harties_refresh.py` in the workspace rebuilds the directory, help numbers and events in the right order into the app's seed (each step replaces only what it put there). Research files: `outputs/community-app/directory/` (decisions, food specials), `outputs/community-app/events/raw/` (every helper's records, with the page each came from). Scripts: `harties_directory.py`, `harties_numbers.py`, `harties_events.py`. Code is on branch `directory` of the app (268 tests and 745+ browser checks pass).
