const maxRenderedRows = 300;
const minimumSearchLength = 2;

const searchForm = document.querySelector("#song-search-form");
const searchInput = document.querySelector("#song-search");
const clearButton = document.querySelector("#clear-search");
const resultsBody = document.querySelector("#song-results");
const resultCount = document.querySelector("#result-count");
const emptyState = document.querySelector("#empty-state");
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
    .trim();
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
    .map((song) => ({
      title: String(song.title || "").trim(),
      artist: String(song.artist || "").trim(),
      popularity: String(song.popularity || "").trim(),
      popularityScore: parsePopularity(song.popularity),
      categories: String(song.categories || "").trim(),
      searchText: normalize((song.title || "") + " " + (song.artist || "") + " " + (song.categories || ""))
    }))
    .sort((a, b) => a.title.localeCompare(b.title) || a.artist.localeCompare(b.artist));
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

function render() {
  const query = searchInput.value.trim();
  const normalizedQuery = normalize(query);

  if (normalizedQuery.length < minimumSearchLength) {
    resultsBody.innerHTML = "";
    emptyState.textContent = "Type at least 2 characters to search.";
    emptyState.hidden = false;
    resultCount.textContent = `${songs.length.toLocaleString()} songs loaded`;
    return;
  }

  const matches = songs.filter((song) => song.searchText.includes(normalizedQuery));
  const visibleMatches = matches.slice(0, maxRenderedRows);

  resultsBody.innerHTML = visibleMatches.map((song) => `
    <tr>
      <td data-label="Title">${highlight(song.title, query)}</td>
      <td data-label="Artist">${highlight(song.artist, query)}</td>
      <td data-label="Categories">${highlight(song.categories || "-", query)}</td>
    </tr>
  `).join("");

  emptyState.hidden = matches.length !== 0;
  const shownText = matches.length > maxRenderedRows ? `, showing first ${maxRenderedRows}` : "";
  resultCount.textContent = `${matches.length.toLocaleString()} song${matches.length === 1 ? "" : "s"}${shownText}`;
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

  if (titleIndex === -1 || artistIndex === -1) {
    throw new Error("CSV must include title and artist columns.");
  }

  return nonEmptyRows.map((items) => ({
    title: items[titleIndex] || "",
    artist: items[artistIndex] || "",
    popularity: popularityIndex === -1 ? "" : items[popularityIndex] || "",
    categories: categoriesIndex === -1 ? "" : items[categoriesIndex] || ""
  }));
}

function setSongs(nextSongs) {
  songs = indexSongs(nextSongs);
  popularSongs = [...songs]
    .sort((a, b) => b.popularityScore - a.popularityScore || a.title.localeCompare(b.title) || a.artist.localeCompare(b.artist))
    .slice(0, 20);
  renderPopularSongs();
  render();
}

async function loadInitialSongs() {
  try {
    let response = await fetch("songs.csv", { cache: "no-store" });

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
