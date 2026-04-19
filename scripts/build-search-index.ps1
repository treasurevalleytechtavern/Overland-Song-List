param(
  [string]$CsvPath = "songs.csv",
  [string]$IndexPath = "songs.index.json"
)

$ErrorActionPreference = "Stop"

function Normalize-SearchText {
  param([AllowNull()][string]$Value)

  $text = if ($null -eq $Value) { "" } else { [string]$Value }
  $text = $text.ToLowerInvariant().Normalize([Text.NormalizationForm]::FormD)
  $text = [Text.RegularExpressions.Regex]::Replace($text, "\p{Mn}", "")
  $text = [Text.RegularExpressions.Regex]::Replace($text, "[^a-z0-9]+", " ")
  $text = [Text.RegularExpressions.Regex]::Replace($text, "\s+", " ")
  return $text.Trim()
}

function Get-Field {
  param(
    [Parameter(Mandatory = $true)]$Row,
    [Parameter(Mandatory = $true)][string[]]$Names
  )

  foreach ($name in $Names) {
    if ($Row.PSObject.Properties.Name -contains $name) {
      return [string]$Row.$name
    }

    $normalizedName = Normalize-SearchText $name
    $matchingProperty = $Row.PSObject.Properties | Where-Object {
      (Normalize-SearchText $_.Name) -eq $normalizedName
    } | Select-Object -First 1

    if ($null -ne $matchingProperty) {
      return [string]$matchingProperty.Value
    }
  }

  return ""
}

function Get-RankingScore {
  param([AllowNull()][string]$Value)

  $raw = if ($null -eq $Value) { "" } else { [string]$Value }
  $clean = [Text.RegularExpressions.Regex]::Replace($raw, "[^0-9.-]", "")
  $score = 0.0

  if ([double]::TryParse($clean, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$score)) {
    return $score
  }

  return 0
}

function Get-DecadeAliases {
  param([AllowNull()][string]$Value)

  $decade = Normalize-SearchText $Value
  $aliases = New-Object System.Collections.Generic.List[string]

  if (-not [string]::IsNullOrWhiteSpace($decade)) {
    $aliases.Add($decade)
  }

  $fourDigitMatch = [Text.RegularExpressions.Regex]::Match($decade, "^(\d{2})(\d{2})s$")
  $twoDigitMatch = [Text.RegularExpressions.Regex]::Match($decade, "^(\d{2})s$")

  if ($fourDigitMatch.Success) {
    $aliases.Add("$($fourDigitMatch.Groups[2].Value)s")
  }

  if ($twoDigitMatch.Success) {
    $year = [int]$twoDigitMatch.Groups[1].Value
    $prefix = if ($year -le 30) { "20" } else { "19" }
    $aliases.Add("$prefix$($twoDigitMatch.Groups[1].Value)s")
  }

  return $aliases | Sort-Object -Unique
}

function Get-ArtistAliases {
  param([AllowNull()][string]$Artist)

  $normalizedArtist = Normalize-SearchText $Artist
  $aliases = New-Object System.Collections.Generic.List[string]

  if ($normalizedArtist.Contains("the chicks")) {
    $aliases.Add("Dixie Chicks")
  }

  if ($normalizedArtist.Contains("dixie chicks")) {
    $aliases.Add("The Chicks")
  }

  if ($normalizedArtist -eq "lady a" -or $normalizedArtist.StartsWith("lady a ") -or $normalizedArtist.Contains(" lady a ")) {
    $aliases.Add("Lady Antebellum")
  }

  if ($normalizedArtist.Contains("lady antebellum") -or $normalizedArtist.Contains("lady antebullum")) {
    $aliases.Add("Lady A")
  }

  return $aliases | Sort-Object -Unique
}

$resolvedCsvPath = Resolve-Path -LiteralPath $CsvPath
$rows = Import-Csv -LiteralPath $resolvedCsvPath
$indexedRows = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
  $title = Get-Field $row @("title")
  $artist = Get-Field $row @("artist")
  $categories = Get-Field $row @("categories")
  $socialSinging = Get-Field $row @("social_singing")
  $decade = Get-Field $row @("decade")
  $year = Get-Field $row @("year")
  $originalVocal = Get-Field $row @("original_vocal")
  $rankingScore = Get-Field $row @("popularity score", "popularity")

  if ([string]::IsNullOrWhiteSpace($title) -and [string]::IsNullOrWhiteSpace($artist)) {
    continue
  }

  $decadeAliases = Get-DecadeAliases $decade
  $artistAliases = Get-ArtistAliases $artist
  $searchText = Normalize-SearchText "$title $artist $($artistAliases -join ' ') $categories $socialSinging $decade $($decadeAliases -join ' ') $year $originalVocal"
  $titleStarts = Normalize-SearchText $title
  $artistStarts = Normalize-SearchText $artist
  $compactFieldsList = New-Object System.Collections.Generic.List[string]
  $compactTitle = $titleStarts -replace "\s", ""
  $compactArtist = $artistStarts -replace "\s", ""
  $compactArtistAliases = $artistAliases | ForEach-Object { (Normalize-SearchText $_) -replace "\s", "" }
  $compactCategories = (Normalize-SearchText $categories) -replace "\s", ""
  $compactSocialSinging = (Normalize-SearchText $socialSinging) -replace "\s", ""
  $compactDecade = (Normalize-SearchText $decade) -replace "\s", ""
  $compactYear = (Normalize-SearchText $year) -replace "\s", ""
  $compactOriginalVocal = (Normalize-SearchText $originalVocal) -replace "\s", ""

  foreach ($compactField in @($compactTitle, $compactArtist) + $compactArtistAliases + @($compactCategories, $compactSocialSinging, $compactDecade, $compactYear, $compactOriginalVocal)) {
    if (-not [string]::IsNullOrWhiteSpace($compactField)) {
      $compactFieldsList.Add($compactField)
    }
  }

  $fuzzyTermsList = New-Object System.Collections.Generic.List[string]
  $uniqueTerms = $searchText.Split(" ", [StringSplitOptions]::RemoveEmptyEntries) | Sort-Object -Unique

  foreach ($term in $uniqueTerms) {
    $fuzzyTermsList.Add($term)
  }

  $indexedRows.Add([object[]]@(
    $title.Trim(),
    $artist.Trim(),
    $categories.Trim(),
    $searchText,
    [object[]]$compactFieldsList.ToArray(),
    [object[]]$fuzzyTermsList.ToArray(),
    $titleStarts,
    $artistStarts,
    $decade.Trim(),
    $originalVocal.Trim(),
    $year.Trim(),
    $socialSinging.Trim(),
    (Get-RankingScore $rankingScore)
  ))
}

$payload = [ordered]@{
  version = 1
  generatedAt = (Get-Date).ToUniversalTime().ToString("o")
  source = (Split-Path -Leaf $resolvedCsvPath)
  songs = [object[]]$indexedRows
}

$json = $payload | ConvertTo-Json -Compress -Depth 8
[IO.File]::WriteAllText((Join-Path (Get-Location) $IndexPath), $json, [Text.UTF8Encoding]::new($false))

Write-Host "Built $IndexPath with $($indexedRows.Count) songs."
