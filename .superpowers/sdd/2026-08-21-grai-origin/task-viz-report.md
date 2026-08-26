# Raport zadania: wizualizacje dowodowe i pokaz ekranu E2

**Status:** gotowe. Cala suita 183 testy przechodzi, `tsc --noEmit` czysty.
Testy i typecheck puszczone przez `./scripts/rt-web` i przez ssh na Hetznerze -
nic nie bylo uruchamiane lokalnie.

## Commity

| commit | co |
|---|---|
| `c6509de` | E2 jako pokaz rozdzialow: jedna sekcja w kadrze, pominiecie, powtorka |
| `2530c1b` | wizualizacje dowodowe: macierz, histogram offsetow, wstega, chronograf, podniesienie werdyktu |

## Co powstalo

### `web/components/pipeline/` - przejeta reszta, ekran E2 przebudowany

- **`chapters.ts`** (nowy) - podzial strumienia na **osiem rozdzialow narracji**:
  wczytanie, odcisk, harmonia, odsiew i powszechnosc, werdykt wstepny, tekst,
  melodia, werdykt koncowy. Kilka zdarzen sklada sie na jeden rozdzial (odsiew +
  powszechnosc). `verdict` rozstrzyga sie po poziomie, bo to sa dwa rozne momenty.
  Etap spoza slownika dostaje wlasny rozdzial zamiast wypasc z ekranu.
- **`usePokaz.ts`** (nowy) - rezyseria: jeden rozdzial w kadrze, 5 s na rozdzial,
  pominiecie, powtorka. `prefers-reduced-motion` wylacza pokaz w calosci.
- **`PipelineList.tsx`** - dwa tryby. `pokaz`: rozdzial na karcie, kropki postepu,
  przycisk **POMIN DO WYNIKU**, Escape i klik w kadr. `pelny`: caly przebieg plus
  przycisk **ODTWORZ PONOWNIE**.
- **`StageRow.tsx`** - nazwa techniczna etapu jako mikroetykieta krojem o stalej
  szerokosci obok nazwy czytelnej.

Trzy rzeczy, o ktore pytales wprost:

1. **Pokaz nie blokuje wyniku.** Rezyseria zyje wylacznie w `PipelineList`.
   `VerdictCard` dostaje zdarzenia z `useAnalysis` bezposrednio, wiec werdykt
   pojawia sie w swoim czasie niezaleznie od tego, na ktorym rozdziale stoi pokaz.
2. **Pokaz sie konczy.** Po ostatnim rozdziale **zakonczonego** przebiegu ekran
   przechodzi w tryb pelny i tam zostaje. Przebieg, ktory jeszcze trwa, zostaje w
   kadrze i czeka - bo dokladnie to sie wtedy dzieje.
3. **Zdarzenia obecne przy montowaniu to powtorka historii**, nie pokaz: ekran
   otwarty na gotowym wyniku pokazuje wszystko od razu.

**Zero scrollowania rozwiazane inaczej, niz sie wydaje:** rozdzialy poza kadrem
zostaja w dokumencie z atrybutem `hidden`, wiec nie zajmuja miejsca w ukladzie,
ale nie sa odmontowywane. Dzieki temu pominiecie nie odbudowuje polowy drzewa i
`page.test.tsx` (cudzy plik) dalej przechodzi bez zmian.

**Testy:** `web/tests/pipeline.test.tsx` ma teraz **40 testow**. Zadnego z 27
poprzednich nie skasowalem; cztery asercje przepisalem na nowa strukture
(licza rozdzialy widoczne, nie wszystkie wezly). Reguly zostaly w mocy i sa
osobno zabezpieczone: najwyzej jeden `data-accent`, `gated` bez czerwieni i bez
slowa "blad", dwie liczby z rozroznialnymi podpisami DT/DD, brak aktywnego kroku
po zerwaniu strumienia.

### `web/components/viz/` - wizualizacje

| plik | co rysuje | podmienia |
|---|---|---|
| `AlignmentMatrix.tsx` | macierz harmoniczna na canvasie, wypelniana kolumnami w osi zapytania, sciezka wyrownania rysowana po niej, przekatna odniesienia, klamry pokrycia na osiach, krzyz podgladu pod kursorem, lokalne nachylenie sciezki | **`evidence/SimilarityMatrix.tsx`** |
| `OffsetHistogram.tsx` | histogram roznic offsetow, prazek dominujacy w akcencie, prog szumu 0.25 na skali | **nowy panel E4**, nie ma odpowiednika |
| `AlignmentRibbon.tsx` | dwie fale i wstega laczaca wspolny odcinek zapytania z odcinkiem kandydata | **uzupelnienie `evidence/WaveOverlay.tsx`** (odsluch A/B zostaje tam) |
| `VerdictLift.tsx` | podniesienie werdyktu: stara klasa przekreslona, znacznik dojezdzajacy po skali, lista dowodow, ktore doszly pomiedzy | **wzbogacenie `verdict/VerdictCard.tsx`** albo osobna karta pod nia |
| `StreamChronograph.tsx` | pasy etapow na osi czasu przyjscia zdarzen | **nowy, do trybu pelnego E2 albo do case file E10** |
| `geometry.ts`, `motion.ts` | czysta geometria i `useProgress` / `useReducedMotion` | - |

`web/tests/viz.test.tsx` - **29 testow**, w wiekszosci o stanach braku danych.

**Wydajnosc:** macierz idzie przez `ImageData` w rozdzielczosci danych i jedno
`drawImage` na klatke, wiec 400 x 400 kosztuje tyle samo co 8 x 8. Reszta to SVG
o kilkudziesieciu wezlach. Wszystko respektuje `prefers-reduced-motion` przez
`useProgress`, ktory przy zyczeniu ograniczenia ruchu zwraca 1 od pierwszej klatki.
Zadna liczba nie jest chowana za animacja - postep jest wylacznie parametrem
rysowania.

## Czego zabraklo w kontrakcie

To jest najwazniejsza czesc tego raportu. **Cztery z szesciu rzeczy z twojej listy
nie istnieja dzisiaj w `contracts.py` ani w `mock.py`**, wiec nie sa narysowane.
Komponenty sa napisane tak, ze przyjma je bez zmiany API - kazde pole ma juz swoj
prop i swoj stan braku.

### 1. Macierz podobienstwa harmonicznego - **najwiekszy brak**

`HarmonicResult` niesie `alignment_path`, `qmax_score`, `coverage`,
`chord_sequence`, ale **nie niesie samej macierzy**. Specyfikacja 7.2 pisze
"Ta sama macierz jest artefaktem UI ... i nie kosztuje nic dodatkowo" - koszt jest
zerowy po stronie liczenia, ale pola w kontrakcie nie ma.

Dzis panel rysuje sciezke na siatce ramek z przekatna odniesienia i pisze wprost,
ze tla nie ma czym wypelnic. Z macierza staje sie tym, co spec nazywa najbardziej
przekonujacym dowodem w systemie.

**Prosba:** `HarmonicResult.similarity_matrix: list[list[float]] | None`, wartosci
0..1, indeksowana `[ramka_zapytania][ramka_kandydata]`, po binaryzacji progiem
percentylowym. Przy 2 Hz i utworze 180 s to 360 x 360 = ok. 130 tys. liczb na
kandydata - **za duzo na koperte SSE dla wszystkich naraz**. Dwa wyjscia, oba mi
pasuja: albo podprobkowanie do ok. 128 x 128 (wystarcza w zupelnosci, panel i tak
skaluje do kadru), albo macierz wylacznie dla lidera rankingu. Przydalby sie tez
`frame_seconds: float`, zeby osie mogly byc w sekundach zamiast w numerach ramek -
prop `frameSeconds` juz na to czeka.

Drugi, tanszy brak przy tym samym panelu: **`chord_sequence` jest tylko po stronie
kandydata**. Sekwencji akordow zapytania w kontrakcie nie ma nigdzie, wiec nawet
tania macierz zgodnosci akordow (ta, ktora liczyl stary `SimilarityMatrix`) nie ma
z czego powstac. `QueryInfo.chord_sequence: list[str]` zalatwia sprawe.

### 2. Histogram roznic offsetow

`FingerprintResult` niesie `peak_ratio` i `repetitions`, czyli **dwie liczby
wyprowadzone z histogramu**, ale nie sam histogram. To jest o tyle bolesne, ze
wlasnie ten wykres jest jednoczesnie dowodem i obrazkiem: ostry prazek wobec
plaskiego rozkladu widac golym okiem, bez zadnego tlumaczenia.

Dzis panel pokazuje `peak_ratio` jako pasek z zaznaczonym progiem szumu 0.25 i
mowi wprost, ze pelnego rozkladu nie bylo.

**Prosba:** `FingerprintResult.offset_histogram: list[dict] | None`, lista
`{"offset": float, "count": int}`. Kubelkow rzedu 60-200, czyli kilka kilobajtow -
to jest tani i bardzo oplacalny dodatek. Prop `bins` juz go przyjmie.

### 3. Chromagram - **nie zbudowalem renderera**

Dwanascie klas wysokosci w czasie nie istnieje w kontrakcie w zadnej postaci.
Swiadomie **nie napisalem komponentu**, ktory zawsze mowilby tylko "brak danych" -
to bylby martwy plik. Jesli dolozysz zadanie po stronie backendu, dopisze go w
godzine.

**Potrzebne:** `QueryInfo.chromagram` i `HarmonicResult.candidate_chromagram`,
`list[list[float]]` 12 x N po agregacji do ok. 2 Hz, znormalizowane 0..1, plus
`frame_seconds`. Przy 180 s to 12 x 360 = 4320 liczb na strone, czyli rozmiar
zupelnie znosny.

### 4. Konstelacja landmarkow odcisku - **nie zbudowalem renderera**, ten sam powod

Punkty w przestrzeni czas-czestotliwosc i pary spinajace je w trojki nie sa nigdzie
wystawione. Kontrakt niesie tylko `matched_hashes` jako licznik.

**Potrzebne:** `FingerprintResult.landmarks: list[dict]` z
`{"t": float, "f": float, "matched": bool}` i opcjonalnie
`pairs: list[[int, int]]` na linie miedzy pikami. Wystarczy okno wokol
`query_span`, nie caly utwor - 200-500 punktow robi caly efekt.

### 5 i 6 - **sa i sa narysowane**

Sciezka wyrownania miedzy przebiegami: `alignment.query_span` i `candidate_span`
wystarczaja, probki fali licze w przegladarce z `audio_url` (`AlignmentRibbon`
przyjmuje je propem, zeby nie dotykac `lib/`). Strumien zdarzen: `StreamChronograph`
mierzy czasy przyjscia sam, a `VerdictLift` korzysta z `previous_class` i
`previous_probability`, ktore atrapa juz wklada do werdyktu poziomu 2 - dziekuje
temu, kto to przewidzial.

## Zaleznosci

**Zadnych nowych.** Wszystko na `react` i natywnym canvasie/SVG. `package.json`
nietkniety.

## Do zrobienia przez integracje

1. `AlignmentMatrix` zamiast `SimilarityMatrix` w `app/EvidencePanels.tsx`.
   Nowe propy: `path` przyjmuje `alignment_path` bez zmian, doszly `matrix`,
   `frameSeconds`, `candidateName`. Stare `queryChords` / `candidateChords` juz nie sa
   potrzebne - panel nie liczy macierzy z akordow, tylko mowi, ze macierzy nie ma.
2. `OffsetHistogram` jako nowy panel E4, zasilany z koperty odcisku
   (`peak_ratio`, `matched_hashes`, `repetitions`, `offset`).
3. `VerdictLift` pod karta E3 albo w niej. `changedBy` liczy `zmianyMiedzyWerdyktami(events)`.
4. `StreamChronograph` w trybie pelnym E2 albo w case file E10. Wymaga listy zdarzen
   **na zywo** - zamontowany na gotowej historii uczciwie powie, ze nie ma czego mierzyc.
5. `AlignmentRibbon` obok `WaveOverlay`: probki policz przez `input/peaks.ts`
   (`peaksZAdresu`) i podaj propem.

## Jedna rzecz, ktorej nie zrobilem po twojemu

Zdanie rozdzialu "tekst" brzmi u mnie *"Porownujemy warstwe slowna, o ile system
ufa wlasnej transkrypcji"*, a nie *"bramka odrzucila transkrypcje, wiec separujemy
wokal"*. Powod: odrzucenie przez bramke **zdarza sie albo nie** i zalezy od
materialu. Zdanie rozdzialu opisuje pytanie, na ktore rozdzial odpowiada, a to, co
naprawde zaszlo, mowi wiersz pod nim - z powodem odrzucenia i nastepnym krokiem,
gdy bramka faktycznie zadzialala. Wpisanie tego na stale w naglowek sekcji byloby
pierwsza atrapa na tym ekranie.
