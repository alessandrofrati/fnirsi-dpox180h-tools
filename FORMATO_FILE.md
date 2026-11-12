# Formato dei file del FNIRSI DPOX180H

Specifica dei file salvati dall'oscilloscopio con il firmware V40, usata da `fnirsi.py` e dal visore. Le voci segnate "inferito" vengono dal confronto fra file salvati con impostazioni diverse.

## Forme d'onda (`/Waveform/N.wav`)

Il file non è un WAV audio. **Tutti i campi sono big-endian**, campioni compresi.

### Tabella iniziale (7 × u32)

| Offset | Campo |
|---|---|
| 0x00 | inizio delle impostazioni (sempre 0x32) |
| 0x04 | lunghezza delle impostazioni |
| 0x08 | inizio della miniatura |
| 0x0C | lunghezza della miniatura |
| 0x10 | inizio dei dati |
| 0x14 | lunghezza dei dati |
| 0x18 | lunghezza totale del file |

### Miniatura
`u16 larghezza`, `u16 altezza` (di solito 102×54), poi larghezza × altezza pixel RGB565, dalla riga in alto.

### Dati
- **Campioni:** sono **u16** e partono **esattamente** dall'inizio del blocco dati (valore a 0x10), senza byte di salto. 1600 conteggi per divisione verticale, 8 divisioni sullo schermo.
- **Ordine dei canali:** prima tutti i campioni di CH1 (se il byte 0x66 vale 1), poi tutti quelli di CH2 (se il byte 0xA6 vale 1).
- **Campioni per canale:** u32 a **0x12D**.
- **Campioni di un'acquisizione:** u32 a **0x11D**, pari a frequenza × tempo/div × 12 divisioni, cioè una schermata.
- **Acquisizioni:** ogni canale contiene 0x12D / 0x11D acquisizioni della stessa finestra, una dopo l'altra. Sono 1 o 2 alle basi dei tempi lente, 3 a 2 µs/div, 10 a 50–100 ns/div.
  - **La prima è quella che si vedeva sullo schermo:** coincide con la miniatura.
  - Le altre sono acquisizioni separate, non la continuazione della prima.
- **Campioni vuoti:** ogni acquisizione può cominciare con alcuni campioni a zero.
- **Conversione in volt:** V = (conteggi / 1600 − zero) × V/div, con lo zero in divisioni dal basso (vedi sotto).

### Impostazioni (dall'offset 0x32)

| Offset | Tipo | Significato |
|---|---|---|
| 0x62 + k·0x40 | blocco canale (k = 0 CH1, 1 CH2) | |
| +0x04 (0x66 / 0xA6) | u8 | canale acceso |
| +0x07 (0x69 / 0xA9) | u8 | indice della portata V/div (9 = 10 mV, 10 = 5 mV), inferito |
| +0x0C (0x6E / 0xAE) | u64 | V/div in µV |
| +0x14 (0x76 / 0xB6) | u64 | copia del V/div |
| +0x1C (0x7E / 0xBE) | u16 | posizione dello zero in pixel dal basso, 25 px per divisione, con uno scarto di 2: zero in divisioni = (px − 2) / 25 (copia a +0x1E) |
| 0x112 / 0x11D / 0x121 | u32 | lunghezze di record (0x11D = campioni di un'acquisizione) |
| 0x12D | u32 | campioni per canale nel file |
| 0x139 | u64 | frequenza di campionamento in Hz |
| 0x1D4 | u8 | indice della base dei tempi (28 = 2 ms, 26 = 500 µs), inferito |
| 0x1D5 | u64 | tempo/div in picosecondi |
| 0x1E9 | u16 | N1 = numero di voci della tabella a 0x2B8 |
| 0x2B8 | N1 × (3 × u32) | tabella variabile: sposta in avanti tutti i campi successivi di 12·(N1−1) byte |
| fine | N2 × u16 | N2 = 24 nei file esaminati |

Lunghezza delle impostazioni = 0x353 + 12·N1 + 2·N2. Nei file esaminati: 0x38F, 0x39B e 0x3A7 per N1 = 1, 2 e 3.

Un errore facile da fare: leggere i campioni little-endian con uno scarto di qualche byte. La traccia sembra quasi giusta, ma risulta spostata e ha salti sporadici di ±256 conteggi.

## Screenshot (`/Screenshots/N.bmp`)
- **Formato:** BMP standard 320×240, 16 bit, BI_BITFIELDS RGB565 (maschere F800/07E0/001F).
- **Pixel:** cominciano a **0x2710** (10000).
- **Miniatura:** tra 0x46 e 0x2710 c'è una miniatura per la galleria dello strumento: `u16 larghezza`, `u16 altezza` (75×36), poi pixel RGB565, **little-endian**, dalla riga in alto.
- **biSizeImage:** il campo è fisso a 0xBB800 ed è sbagliato, ma i programmi di grafica lo ignorano.

## Altri file e comportamento via USB
- **`number_table.sys`:** `/Waveform/number_table.sys` e `/Screenshots/number_table.sys` sono file nascosti. Contengono un u16 con il numero di file, poi un elenco di u16 con i numeri usati, e spiegano perché la numerazione riparte dopo una cancellazione.
- **File cancellati dal computer:** lo strumento li toglie dal proprio elenco quando si apre la sua galleria.
- **Modalità USB:** dal menu "USB sharing" lo strumento si presenta solo come disco USB (mass storage, VID:PID 0483:5720). Mentre è collegato non acquisisce e non accetta comandi: non c'è SCPI né porta seriale.
- **macOS:** su macOS lo strumento si blocca con le letture grandi che il sistema fa normalmente. Leggere a blocchi di 4 kB con la cache disattivata (`F_NOCACHE`) funziona sempre.
