# 06. Źródła „gorących” informacji (newsy, kontuzje, składy)

„Zweryfikowane” oznacza, że feed zwrócił aktualne wpisy 2026-10-17. Pozostałe pozycje trzeba sprawdzić przed użyciem.

## Feedy RSS per liga

### Ekstraklasa
| Źródło | URL | Status |
|---|---|---|
| WP SportoweFakty | https://sportowefakty.wp.pl/rss.xml (filtr kategorii `/pilka-nozna`) | zweryfikowane |
| Weszło | https://weszlo.com/feed/ | zweryfikowane |
| Interia Sport | https://sport.interia.pl/feed | według feeder.co działa |
| Meczyki.pl (T. Włodarczyk, newsy na wyłączność) | brak RSS, scraping lub Google News | — |
| Przegląd Sportowy, 90minut.pl | blokują odczyt, użyć Google News | — |

### Championship
| Źródło | URL | Status |
|---|---|---|
| Sky Sports Championship | https://www.skysports.com/rss/11688 | zweryfikowane |
| Football League World | https://footballleagueworld.co.uk/feed/ | zweryfikowane; szybko łapie plotki o zwolnieniach trenerów |
| BBC Championship | https://feeds.bbci.co.uk/sport/football/championship/rss.xml | nie sprawdzone |
| Gazety lokalne (Reach „Live”) | przez Google News per klub | — |

### 2. Bundesliga
| Źródło | URL | Status |
|---|---|---|
| kicker 2. Bundesliga | https://newsfeed.kicker.de/news/2-bundesliga | zweryfikowane |
| kicker, przewidywane składy (voraussichtliche Aufstellung) | strony meczów (zwracają 403, potrzebny przeglądarkowy user agent) | — |

### Eredivisie
| Źródło | URL | Status |
|---|---|---|
| Voetbal International | https://www.vi.nl/feed/news.xml, push przez WebSub: https://pb-api.vi.nl/websub/hub | zweryfikowane |
| VoetbalPrimeur | https://www.voetbalprimeur.nl/feed/news.xml, WebSub: https://api.voetbalprimeur.nl/websub/hub; publikuje „Vermoedelijke opstelling” | zweryfikowane |

## Kontuzje i zawieszenia
- **Sportsgambler:** https://www.sportsgambler.com/injuries/football/ — Championship, 2. Bundesliga, Eredivisie; **bez Ekstraklasy**.
- **Transfermarkt:** `/{liga}/verletztespieler/wettbewerb/{GB2|L2|NL1|PL1}` — najlepiej ustrukturyzowane, z Ekstraklasą, ale blokuje boty.
- **API-Football `/injuries`:** pokrycie sprawdzamy przez `/leagues?id=X&season=2026` (pole `coverage.injuries`). ID lig do weryfikacji: Ekstraklasa 106, Championship 40, 2. Bundesliga 79, Eredivisie 88.
- **FotMob / Sofascore:** przewidywane składy i lista nieobecnych przez nieoficjalny JSON, kruchy.
- **Flashscore:** nieobecni zawodnicy, tylko scraping.

## Potwierdzone składy (około 60 min przed meczem)
- Najszybciej publikują je konta klubów na X. FotMob i Sofascore pokazują je 1–3 min później, API-Football kilka minut po nich.
- **Rekomendacja:** od 75 min przed meczem odpytywać FotMob co 60–90 s, API-Football jako backup.

## X / Twitter i alternatywy
- **X API:** od 02.2026 nowi użytkownicy płacą za użycie, $0,005 za przeczytany post. 100 kont po 20 postów dziennie to około $300/mies. **Za drogo.**
- **Nitter:** wezwania do zaprzestania działalności w 2026, nitter.net offline. **Nie polegać.**
- **Bluesky:** natywny RSS `https://bsky.app/profile/{handle}/rss`. Niewielu reporterów.
- **Kogo śledzić (ręcznie lub przez Google News):** Tomasz Włodarczyk (PL), Alan Nixon (Championship), lokalni reporterzy klubowi.

## Google News, Reddit, YouTube
- **Google News RSS:**
  `https://news.google.com/rss/search?q="Hertha+BSC"+(Verletzung+OR+Ausfall+OR+Aufstellung)+when:1d&hl=de&gl=DE&ceid=DE:de`
  - Ustawienia regionalne: `pl/PL/PL:pl`, `en-GB/GB/GB:en`, `nl/NL/NL:nl`.
  - Linki są przekierowaniami, więc deduplikujemy po tytule.
- **Reddit:** `https://www.reddit.com/r/{sub}/new/.rss`, z właściwym user agentem.
- **YouTube:** `https://www.youtube.com/feeds/videos.xml?channel_id=...`. Konferencje prasowe: napisy przez `yt-dlp --write-auto-subs --skip-download`, potem do LLM.

## Ruch kursów jako zastępnik newsów
- **BetExplorer dropping odds** (zweryfikowane): https://www.betexplorer.com/football/dropping-odds/ — filtrować po kraju.
- **Reguła:** Pinnacle lub konsensus rynku przesuwa się o więcej niż 5–8% bez newsa → flaga „niewyjaśniony ruch” i celowane wyszukiwanie newsów o obu drużynach.

## Słowa kluczowe do zapytań per język
- **PL:** kontuzja, uraz, zawieszony, skład, zwolniony, zaległości.
- **EN:** injury, team news, sacked, suspended.
- **DE:** Verletzung, Ausfall, Sperre, Aufstellung, entlassen.
- **NL:** blessure, geschorst, opstelling, ontslagen.

## Pipeline (docelowo F5)

| Okno przed meczem | Co odpytujemy | Jak często |
|---|---|---|
| 48–24 h | RSS | co 30 min |
| | strony kontuzji | co 6 h |
| 24–3 h | RSS i Google News | co 10 min |
| | dropping odds | co 15 min |
| 3 h – 75 min | wszystko | co 5 min |
| 75 min – 0 | składy | co 60–90 s |

**Przetwarzanie wpisów:**
1. **Deduplikacja:** normalizacja URL (rozwijanie przekierowań Google), hash, podobieństwo tytułów (MinHash lub SimHash), grupowanie po drużynie i zdarzeniu w oknie 6 h.
2. **Ekstrakcja LLM:** najpierw tani filtr trafności, potem ustrukturyzowany JSON:
   `{team, player, flag_type: injury|suspension|lineup_change|manager_change|conflict|finance|travel|weather|motivation, status: confirmed|doubtful|rumour, source_tier, impact_estimate, evidence_url}`
3. **Poziomy źródeł:** klub lub oficjalne = 1, duże media krajowe = 2, agregatory i Reddit = 3.
4. **Alert:** nowa flaga „confirmed” z poziomu 1–2, której kurs jeszcze nie uwzględnia, albo spadek kursu bez newsa.
