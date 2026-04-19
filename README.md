# Karaoke Song Search

A static, no-login karaoke song search page for title, artist, categories, social singing, decade, year, and original vocal. Visitors can search the published song list only; there is no public upload control.

## Update The Public Song List

Edit the public `songs.csv` with these exact headers:

```csv
title,artist,year,decade,original_vocal,categories,social_singing
Friends in Low Places,Garth Brooks,1990,1990s,Male,Country,Group Songs
Jolene,Dolly Parton,1973,1970s,Female,Country,
```

Optional hidden ranking column: `popularity` or `popularity score`. Use a number from 1 to 1000. Higher numbers break ties after normal search/filter relevance.

If a categories value contains commas, wrap that field in quotes.

Update the public `songs.csv` file used by the site, then rebuild the search index. `data/songs.csv` is only a fallback copy for the app and should use the same public CSV structure if you keep it.

## Embed It

The cleanest setup is to host the search app as a real static page, then embed it in GoDaddy with an iframe.

## GitHub Pages Setup

Put these files in the GitHub repo:

```text
index.html
report-song-issue.html
styles.css
app.js
songs.csv
songs.index.json
.nojekyll
assets/overland-bar-logo.png
assets/good-times-karaoke.jpg
scripts/build-search-index.ps1
```

Then enable GitHub Pages:

1. Open the repo on GitHub.
2. Go to **Settings**.
3. Go to **Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Choose the `main` branch and `/root`.
6. Save.

Your page will usually be:

```text
https://treasurevalleytechtavern.github.io/Overland-Song-List/
```

Your CSV should be available at:

```text
https://treasurevalleytechtavern.github.io/Overland-Song-List/songs.csv
```

The page will try to load the faster JSON index first:

```text
https://treasurevalleytechtavern.github.io/Overland-Song-List/songs.index.json
```

If the JSON index is missing, it falls back to `songs.csv`, but that is slower for very large song lists.

## Build The Search Index

After updating `songs.csv`, rebuild the JSON index before pushing to GitHub:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-search-index.ps1 -CsvPath songs.csv -IndexPath songs.index.json
```

Commit or upload both:

```text
songs.csv
songs.index.json
```

The JSON index precomputes normalized search fields, typo-match terms, and category search data so visitors do not have to build all of that in their browser.

## GoDaddy Embed

After GitHub Pages is live, paste only this into GoDaddy's HTML section:

```html
<iframe
  src="https://treasurevalleytechtavern.github.io/Overland-Song-List/"
  title="Overland Bar karaoke song search"
  style="width: 100%; height: 900px; border: 0; background: #050505;"
  loading="lazy"
></iframe>
```

This avoids GoDaddy rewriting the app's CSS and JavaScript.

## GoDaddy HTML Block Fallback

If you are using GoDaddy's HTML section without an iframe, copy the contents of `godaddy-embed.html` and paste that whole block into the HTML section. That version includes its own CSS and JavaScript because GoDaddy HTML sections usually do not load local `styles.css` or `app.js` files.

In `godaddy-embed.html`, this line points to the public CSV:

```js
var songCsvUrl = "https://raw.githubusercontent.com/treasurevalleytechtavern/Overland-Song-List/main/songs.csv";
```

The CSV should be on the same website/domain when possible. Some file hosts block browser fetches from embedded code.

For large lists, the search waits until someone types at least 2 characters and renders only the first 100 matches. The dice button can show 5 randomized Female original-vocal suggestions and 5 randomized Male original-vocal suggestions when someone wants quick ideas.

Available Songs uses strict matches first. If there are 1 to 4 strict matches, a Similar Songs section appears underneath. Similar Songs uses the same artist when the search looks like a song title, and shared categories when the search looks like an artist/category/decade/year search. Typo matching is only used when there are zero strict matches.

The browse buttons are lightweight stacked filters. They can combine terms like `Genre: Rock; Decade: 70s; Original vocal: Female`, then run the same search logic. `categories`, `social_singing`, `decade`, `original vocal`, and `year` are indexed for search but are not shown as visible columns.

Current browse groups:

```text
Original vocal: Male, Female, Mixed
Genre: Pop, Rock, Country, Hip-Hop, Rap, R&B, Soul, Alternative / Indie, Emo / Pop Punk, Metal / Hard Rock
Decade: 70s, 80s, 90s, 2000s, 2010s
Social singing: Duet, Group Songs
```

## Preview It

Because the songs are loaded from a CSV file, serve the folder locally:

```powershell
python -m http.server 8000
```

Then open `http://localhost:8000`.
