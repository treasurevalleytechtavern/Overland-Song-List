const maxRenderedRows = 300;
const minimumSearchLength = 2;
const fuzzyResultLimit = 80;
const requestSongUrl = "https://overlandbar.com/request-a-song";

const searchForm = document.querySelector("#song-search-form");
const searchInput = document.querySelector("#song-search");
const clearButton = document.querySelector("#clear-search");
const browseButtons = document.querySelectorAll(".browse-button");
const resultsBody = document.querySelector("#song-results");
const resultCount = document.querySelector("#result-count");
const emptyState = document.querySelector("#empty-state");
const similarPanel = document.querySelector("#similar-panel");
const similarBody = document.querySelector("#similar-results");
const similarTitle = document.querySelector("#similar-title");
const popularBody = document.querySelector("#popular-results");
const popularEmptyState = document.querySelector("#popular-empty-state");

let songs = [];
let popularSongs = [];
let searchTimer = 0;

function normalize(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenize(value) {
  return normalize(value).split(" ").filter(Boolean);
}

function getDecadeAliases(value) {
  const decade = normalize(value);
  const aliases = new Set();
  const fourDigitMatch = decade.match(/^(\d{2})(\d{2})s$/);
  const twoDigitMatch = decade.match(/^(\d{2})s$/);

  if (decade) {
    aliases.add(decade);
  }

  if (fourDigitMatch) {
    aliases.add(`${fourDigitMatch[2]}s`);
  }

  if (twoDigitMatch) {
    const year = Number(twoDigitMatch[1]);
    aliases.add(`${year <= 30 ? "20" : "19"}${twoDigitMatch[1]}s`);
  }

  return Array.from(aliases);
}

function getSearchPieces(song) {
  const decadeAliases = getDecadeAliases(song.decade);
  return [
    song.title,
    song.artist,
    song.categories,
    song.decade,
    ...decadeAliases,
    song.originalVocal
  ].filter(Boolean);
}

function parsePopularity(value) {
  const score = parseFloat(String(value || "").replace(/[^0-9.-]/g, ""));
  return isFinite(score) ? score : 0;
}

function findHeader(headers, candidates) {
  for (let index = 0; index < candidates.length; index += 1) {
    const headerIndex = headers.indexOf(candidates[index]);

    if (headerIndex !== -1) {
      return headerIndex;
    }
  }

  return -1;
}

function indexSongs(nextSongs) {
  return nextSongs
    .filter((song) => song.title || song.artist)
    .map((song) => {
      const title = String(song.title || "").trim();
      const artist = String(song.artist || "").trim();
      const popularity = String(song.popularity || "").trim();
      const categories = String(song.categories || "").trim();
      const decade = String(song.decade || "").trim();
      const originalVocal = String(song.originalVocal || "").trim();
      const searchPieces = getSearchPieces({ title, artist, categories, decade, originalVocal });
      const searchText = normalize(searchPieces.join(" "));
      const compactFields = [
        normalize(title).replace(/\s/g, ""),
        normalize(artist).replace(/\s/g, ""),
        normalize(categories).replace(/\s/g, ""),
        normalize(decade).replace(/\s/g, ""),
        normalize(originalVocal).replace(/\s/g, "")
      ].filter(Boolean);

      return {
        title,
        artist,
        popularity,
        popularityScore: parsePopularity(popularity),
        categories,
        decade,
        originalVocal,
        searchText,
        compactFields,
        titleStarts: normalize(title),
        artistStarts: normalize(artist),
        fuzzyTerms: Array.from(new Set(tokenize(searchPieces.join(" "))))
      };
    })
    .sort((a, b) => a.title.localeCompare(b.title) || a.artist.localeCompare(b.artist));
}

function hydrateIndexedSongs(indexPayload) {
  const rows = Array.isArray(indexPayload) ? indexPayload : indexPayload.songs;

  if (!Array.isArray(rows)) {
    throw new Error("Search index is not in the expected format.");
  }

  return rows
    .map((row) => {
      const compactFieldSource = Array.isArray(row[6])
        ? row[6]
        : row[6] && Array.isArray(row[6].value)
          ? row[6].value
          : null;
      const fuzzyTermSource = Array.isArray(row[7])
        ? row[7]
        : row[7] && Array.isArray(row[7].value)
          ? row[7].value
          : null;
      const title = String(row[0] || "").trim();
      const artist = String(row[1] || "").trim();
      const categories = String(row[2] || "").trim();
      const popularity = String(row[3] || "").trim();
      const popularityScore = typeof row[4] === "number" ? row[4] : parsePopularity(popularity);
      const decade = String(row[10] || "").trim();
      const originalVocal = String(row[11] || "").trim();
      const searchPieces = getSearchPieces({ title, artist, categories, decade, originalVocal });
      const searchText = String(row[5] || normalize(searchPieces.join(" ")));
      const compactFields = compactFieldSource
        : [normalize(title).replace(/\s/g, ""), normalize(artist).replace(/\s/g, ""), normalize(categories).replace(/\s/g, ""), normalize(decade).replace(/\s/g, ""), normalize(originalVocal).replace(/\s/g, "")].filter(Boolean);
      const fuzzyTerms = fuzzyTermSource
        : Array.from(new Set(tokenize(searchPieces.join(" "))));

      return {
        title,
        artist,
        categories,
        decade,
        originalVocal,
        popularity,
        popularityScore,
        searchText,
        compactFields,
        fuzzyTerms,
        titleStarts: String(row[8] || normalize(title)),
        artistStarts: String(row[9] || normalize(artist))
      };
    })
    .filter((song) => song.title || song.artist)
    .sort((a, b) => a.title.localeCompare(b.title) || a.artist.localeCompare(b.artist));
}

function editDistanceWithin(a, b, maxDistance) {
  if (Math.abs(a.length - b.length) > maxDistance) {
    return maxDistance + 1;
  }

  let previous = Array.from({ length: b.length + 1 }, (_, index) => index);

  for (let row = 1; row <= a.length; row += 1) {
    const current = [row];
    let rowMinimum = current[0];

    for (let column = 1; column <= b.length; column += 1) {
      const cost = a[row - 1] === b[column - 1] ? 0 : 1;
      const value = Math.min(
        previous[column] + 1,
        current[column - 1] + 1,
        previous[column - 1] + cost
      );

      current[column] = value;
      rowMinimum = Math.min(rowMinimum, value);
    }

    if (rowMinimum > maxDistance) {
      return maxDistance + 1;
    }

    previous = current;
  }

  return previous[b.length];
}

function allowedTypoDistance(term) {
  if (term.length < 4) {
    return 0;
  }

  if (term.length < 8) {
    return 1;
  }

  return 2;
}

function fuzzyRank(song, queryTerms) {
  let totalDistance = 0;
  const meaningfulTerms = queryTerms.filter((term) => term.length >= 3);

  if (meaningfulTerms.length >= 2) {
    const compactQuery = meaningfulTerms.join("");
    const phraseDistance = allowedTypoDistance(compactQuery);

    if (song.compactFields.some((field) => field.includes(compactQuery))) {
      return 0;
    }

    if (!song.fuzzyTerms.some((term) => meaningfulTerms.includes(term))) {
      return null;
    }

    if (compactQuery.length >= 7 && song.compactFields.some((field) => editDistanceWithin(compactQuery, field, phraseDistance) <= phraseDistance)) {
      return phraseDistance;
    }
  }

  for (const queryTerm of queryTerms) {
    const maxDistance = allowedTypoDistance(queryTerm);
    let bestDistance = maxDistance + 1;

    for (const songTerm of song.fuzzyTerms) {
      if (songTerm.includes(queryTerm) || queryTerm.includes(songTerm)) {
        bestDistance = 0;
        break;
      }

      if (maxDistance > 0) {
        bestDistance = Math.min(bestDistance, editDistanceWithin(queryTerm, songTerm, maxDistance));
      }

      if (bestDistance === 0) {
        break;
      }
    }

    if (bestDistance > maxDistance) {
      return null;
    }

    totalDistance += bestDistance;
  }

  return totalDistance;
}

function renderRequestSong(query) {
  const requestUrl = `${requestSongUrl}?song=${encodeURIComponent(query)}`;
  resultsBody.innerHTML = "";
  if (similarPanel) {
    similarPanel.hidden = true;
  }
  emptyState.innerHTML = `
    <span>No songs found for "${escapeHtml(query)}".</span>
    <a class="request-song-button" href="${requestUrl}" target="_top">Request a song</a>
  `;
  emptyState.hidden = false;
  resultCount.textContent = "0 songs";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  })[char]);
}

function highlight(value, query) {
  const safeValue = escapeHtml(value);
  const term = query.trim();

  if (!term) {
    return safeValue;
  }

  const index = normalize(value).indexOf(normalize(term));

  if (index === -1) {
    return safeValue;
  }

  const raw = String(value);
  const before = escapeHtml(raw.slice(0, index));
  const match = escapeHtml(raw.slice(index, index + term.length));
  const after = escapeHtml(raw.slice(index + term.length));
  return `${before}<mark>${match}</mark>${after}`;
}

function renderPopularSongs() {
  if (!popularBody || !popularEmptyState) {
    return;
  }

  popularBody.innerHTML = popularSongs.map((song) => `
    <tr>
      <td data-label="Title">${escapeHtml(song.title)}</td>
      <td data-label="Artist">${escapeHtml(song.artist)}</td>
      <td data-label="Categories">${escapeHtml(song.categories || "-")}</td>
    </tr>
  `).join("");

  popularEmptyState.hidden = popularSongs.length !== 0;
}

function getCategoryTerms(song) {
  return tokenize(song.categories).filter((term) => term.length >= 3);
}

function renderSongRows(songList, query = "") {
  return songList.map((song) => `
    <tr>
      <td data-label="Title">${query ? highlight(song.title, query) : escapeHtml(song.title)}</td>
      <td data-label="Artist">${query ? highlight(song.artist, query) : escapeHtml(song.artist)}</td>
      <td data-label="Categories">${query ? highlight(song.categories || "-", query) : escapeHtml(song.categories || "-")}</td>
    </tr>
  `).join("");
}

function renderSimilarSongs(matches, query, queryTerms) {
  if (!similarPanel || !similarBody || !similarTitle) {
    return;
  }

  similarPanel.hidden = true;
  similarBody.innerHTML = "";

  if (matches.length === 0 || matches.length >= 10) {
    return;
  }

  const matchSet = new Set(matches);
  const normalizedQuery = normalize(query);
  const artistIntent = matches.some((song) => song.artistStarts.includes(normalizedQuery));
  const titleIntent = matches.some((song) => song.titleStarts.includes(normalizedQuery));
  let similarSongs = [];

  if (titleIntent && !artistIntent) {
    const artists = new Set(matches.map((song) => normalize(song.artist)).filter(Boolean));
    similarSongs = songs.filter((song) => !matchSet.has(song) && artists.has(normalize(song.artist)));
    similarTitle.textContent = "More by this artist";
  } else {
    const categoryTerms = new Set(matches.flatMap(getCategoryTerms));

    similarSongs = songs
      .map((song) => {
        if (matchSet.has(song)) {
          return null;
        }

        const overlap = getCategoryTerms(song).filter((term) => categoryTerms.has(term)).length;
        return overlap ? { song, overlap } : null;
      })
      .filter(Boolean)
      .sort((a, b) => b.overlap - a.overlap || b.song.popularityScore - a.song.popularityScore || a.song.title.localeCompare(b.song.title))
      .map((match) => match.song);

    similarTitle.textContent = "Songs in a similar lane";
  }

  const visibleSimilarSongs = similarSongs.slice(0, Math.max(0, 10 - matches.length));

  if (visibleSimilarSongs.length === 0) {
    return;
  }

  similarBody.innerHTML = renderSongRows(visibleSimilarSongs);
  similarPanel.hidden = false;
}

function render() {
  const query = searchInput.value.trim();
  const normalizedQuery = normalize(query);

  if (normalizedQuery.length < minimumSearchLength) {
    resultsBody.innerHTML = "";
    if (similarPanel) {
      similarPanel.hidden = true;
    }
    emptyState.textContent = "Type at least 2 characters to search.";
    emptyState.hidden = false;
    resultCount.textContent = `${songs.length.toLocaleString()} songs loaded`;
    return;
  }

  const queryTerms = tokenize(query);
  let matches = songs.filter((song) => {
    if (queryTerms.length === 1) {
      return song.fuzzyTerms.includes(queryTerms[0]);
    }

    return song.searchText.includes(normalizedQuery);
  });
  let usedTypoMatching = false;

  if (queryTerms.length && matches.length === 0) {
    const exactMatches = new Set(matches);
    const fuzzyMatches = [];

    for (const song of songs) {
      if (exactMatches.has(song)) {
        continue;
      }

      const rank = fuzzyRank(song, queryTerms);

      if (rank !== null) {
        fuzzyMatches.push({ song, rank });
      }
    }

    fuzzyMatches
      .sort((a, b) => a.rank - b.rank || b.song.popularityScore - a.song.popularityScore || a.song.title.localeCompare(b.song.title))
      .slice(0, fuzzyResultLimit)
      .forEach((match) => matches.push(match.song));

    usedTypoMatching = fuzzyMatches.length > 0;
  }

  const visibleMatches = matches.slice(0, maxRenderedRows);

  if (matches.length === 0) {
    renderRequestSong(query);
    return;
  }

  resultsBody.innerHTML = renderSongRows(visibleMatches, query);
  renderSimilarSongs(matches, query, queryTerms);

  emptyState.hidden = matches.length !== 0;
  const shownText = matches.length > maxRenderedRows ? `, showing first ${maxRenderedRows}` : "";
  const typoText = usedTypoMatching ? " including close matches" : "";
  resultCount.textContent = `${matches.length.toLocaleString()} song${matches.length === 1 ? "" : "s"}${typoText}${shownText}`;
}

function parseCsv(csvText) {
  const rows = [];
  let current = "";
  let row = [];
  let inQuotes = false;

  for (let index = 0; index < csvText.length; index += 1) {
    const char = csvText[index];
    const next = csvText[index + 1];

    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(current);
      current = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") {
        index += 1;
      }
      row.push(current);
      rows.push(row);
      row = [];
      current = "";
    } else {
      current += char;
    }
  }

  if (current || row.length) {
    row.push(current);
    rows.push(row);
  }

  const nonEmptyRows = rows.filter((items) => items.some((item) => item.trim()));
  const headerRow = nonEmptyRows.shift() || [];
  const headers = headerRow.map((item) => normalize(item));
  const titleIndex = headers.indexOf("title");
  const artistIndex = headers.indexOf("artist");
  const popularityIndex = findHeader(headers, ["popularity score", "popularity_score", "popularity", "score"]);
  const categoriesIndex = findHeader(headers, ["categories", "category"]);
  const decadeIndex = findHeader(headers, ["decade", "decades"]);
  const originalVocalIndex = findHeader(headers, ["original vocal", "original_vocal", "vocal", "vocals", "voice"]);

  if (titleIndex === -1 || artistIndex === -1) {
    throw new Error("CSV must include title and artist columns.");
  }

  return nonEmptyRows.map((items) => ({
    title: items[titleIndex] || "",
    artist: items[artistIndex] || "",
    popularity: popularityIndex === -1 ? "" : items[popularityIndex] || "",
    categories: categoriesIndex === -1 ? "" : items[categoriesIndex] || "",
    decade: decadeIndex === -1 ? "" : items[decadeIndex] || "",
    originalVocal: originalVocalIndex === -1 ? "" : items[originalVocalIndex] || ""
  }));
}

function setSongs(nextSongs) {
  songs = indexSongs(nextSongs);
  setPreparedSongs(songs);
}

function setPreparedSongs(nextSongs) {
  songs = nextSongs;
  popularSongs = [...songs]
    .sort((a, b) => b.popularityScore - a.popularityScore || a.title.localeCompare(b.title) || a.artist.localeCompare(b.artist))
    .slice(0, 20);
  renderPopularSongs();
  render();
}

async function loadInitialSongs() {
  try {
    let response = await fetch("songs.index.json", { cache: "no-store" });

    if (response.ok) {
      setPreparedSongs(hydrateIndexedSongs(await response.json()));
      return;
    }

    response = await fetch("songs.csv", { cache: "no-store" });

    if (!response.ok) {
      response = await fetch("data/songs.csv", { cache: "no-store" });
    }

    if (!response.ok) {
      throw new Error("Song CSV was not available.");
    }

    setSongs(parseCsv(await response.text()));
  } catch {
    songs = [];
    resultsBody.innerHTML = "";
    emptyState.textContent = "Song list unavailable. Check songs.csv.";
    emptyState.hidden = false;
    resultCount.textContent = "0 songs";
  }
}

searchInput.addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(render, 80);
});

browseButtons.forEach((button) => {
  button.addEventListener("click", () => {
    searchInput.value = button.dataset.search || "";
    window.clearTimeout(searchTimer);
    render();
    searchInput.focus({ preventScroll: true });
  });
});

searchInput.addEventListener("search", render);
searchInput.addEventListener("change", render);
searchInput.addEventListener("keyup", (event) => {
  if (event.key === "Enter") {
    render();
  }
});

if (searchForm) {
  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    window.clearTimeout(searchTimer);
    render();
  });
}

clearButton.addEventListener("click", () => {
  searchInput.value = "";
  searchInput.focus();
  render();
});

loadInitialSongs();
