# FNIRSI DPOX180H: scaricamento, visore e decodifica dei file

Strumenti per l'oscilloscopio portatile FNIRSI DPOX180H (firmware V40), testati su macOS:

- **Scaricamento:** copia i file dallo strumento via USB senza i blocchi che si hanno con il Finder.
- **Lettura dei file:** decodifica correttamente le forme d'onda salvate (`.wav`) e le esporta in CSV.
- **Visore nel browser:** galleria con miniature, scale come sullo strumento, cursori, zoom e decodifica dei bus **I²C**, **UART** e **1-Wire**.

> **English summary.** Tools for the FNIRSI DPOX180H handheld scope (firmware V40). They copy the saved files over USB without the macOS hangs and decode the `.wav` waveform files correctly. The file format is documented in `FORMATO_FILE.md`: everything is big-endian, and each channel holds several acquisitions of the same window. A browser viewer has a thumbnail gallery, scope-like scales, cursors and I²C / UART / 1-Wire decoding. The UI and docs are in Italian.

**Non affiliato con FNIRSI.** Progetto indipendente, nato per leggere i propri file di misura. FNIRSI è un marchio del rispettivo proprietario.

## Requisiti

- Python 3.9 o successivo, senza librerie esterne.
- macOS per lo scaricamento dallo strumento: usa `mount`, `diskutil` e le opzioni di lettura senza cache. La lettura dei file e il visore funzionano ovunque.
- Un browser recente.

## Uso

Sullo strumento: impostazioni → **USB sharing**, poi collega il cavo.

```bash
python3 fnirsi.py visore
```

Si apre il visore nel browser, con la galleria dei file presenti sullo strumento.

- **Galleria:**
  - Miniature con l'etichetta **nuovo** o **sul Mac**.
  - **Scarica selezionati** apre subito le forme d'onda nel visore.
  - **Cancella dallo strumento** chiede conferma prima di cancellare.
  - **Espelli** espelle il disco dello strumento.
- **Visore:**
  - V/div e s/div come sullo strumento (passi 1-2-5, unità automatiche), posizione dello zero, griglia 12 × 8.
  - Tracce separate o sovrapposte.
  - Scelta dell'acquisizione: ogni file ne contiene più di una, e la prima è quella che si vedeva sullo schermo.
  - Zoom trascinando sul grafico, scorrimento con la barra, ◀ ▶ o il trackpad.
  - Cursori Δt e ΔV.
  - Esportazione CSV e PNG.
- **Decodifica bus:**
  - **I²C:** START, STOP, start ripetuto, indirizzo a 7 bit, R/W, ACK e NACK.
  - **UART:** TX e RX, velocità automatica, bit di dati, parità, bit di stop, livelli TTL o RS-232.
  - **1-Wire:** reset, presenza, comandi ROM e DS18B20, CRC, temperatura.

Il visore funziona anche aprendo direttamente `visore_fnirsi_dpox180h.html` nel browser. In quel caso legge i file aperti a mano o trascinati, senza la galleria dello strumento.

Altri comandi:

```bash
python3 fnirsi.py scarica --csv --espelli
```

```bash
python3 fnirsi.py info FILE.wav
```

```bash
python3 fnirsi.py csv --acquisizione 2 FILE.wav
```

I file scaricati vanno in `misure/oscilloscopio_AAAAMMGG`, nella cartella che contiene questo progetto. Si può cambiare con `--dest DIR`.

## Contenuto

| Percorso | Che cos'è |
|---|---|
| `fnirsi.py` | scaricamento, decodifica, CSV e server del visore |
| `visore_fnirsi_dpox180h.html` | il visore |
| `FORMATO_FILE.md` | formato dei file `.wav` e `.bmp`, comportamento via USB |
| `esempi/` | file `.wav` sintetici con traffico I²C, UART e 1-Wire per provare la decodifica |
| `esempi/generatori/` | gli script che li hanno generati |

## Da sapere

- **Blocchi su macOS:** lo strumento si blocca con le letture grandi. Lo script legge 4 kB alla volta senza cache, sempre in un processo separato con un timeout. Se una lettura si blocca, stacca e riattacca il cavo.
- **USB:** lo strumento offre solo il disco USB (mass storage): non c'è SCPI né seriale né acquisizione remota.
- **Decodifica dei bus:** è stata provata sui file sintetici di `esempi/`. Come su qualsiasi oscilloscopio, il protocollo va scelto in base al segnale: un decodificatore legge qualcosa anche da un segnale che non è un bus.

## Licenza

MIT, vedi `LICENSE`.
