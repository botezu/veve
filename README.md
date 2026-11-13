# Vývoj investic – podílové fondy Conseq

Statická stránka pro GitHub Pages. Ukazuje hodnotu investice proti vloženým penězům, za každý fond i celkem.
GitHub Actions každý den stáhne aktuální ceny z conseq.cz, přepočítá data a stránku znovu nasadí.

## Co je v repozitáři

| Soubor | K čemu je |
|---|---|
| `index.html` | samotná stránka (grafy + tabulka) |
| `data/nakupy.csv` | **nákupy** – sem se dopisují nové nákupy |
| `funds.json` | seznam fondů: název, ISIN, `productid` pro stahování z Conseq, varianty názvu |
| `data/prices/*.csv` | historie cen jednotlivých fondů (doplňuje automat) |
| `data/portfolio.json` | spočítaná data pro graf (generuje automat) |
| `scripts/update.py` | stažení cen a výpočet |
| `.github/workflows/update.yml` | denní spuštění a nasazení na GitHub Pages |

---

## Nastavení GitHubu krok za krokem

### 1. Účet
Pokud ho ještě nemáte, založte si účet na <https://github.com/signup>.

### 2. Nový repozitář
1. Vpravo nahoře **+** → **New repository**.
2. **Repository name:** třeba `investice` (bude součástí adresy webu).
3. **Public** – GitHub Pages je na bezplatném účtu jen pro veřejné repozitáře (viz *Soukromí* níže).
4. Nic dalšího nezaškrtávejte (žádné README, .gitignore ani licence) → **Create repository**.

### 3. Nahrání souborů
1. Na stránce prázdného repozitáře klikněte na odkaz **uploading an existing file**.
2. V Průzkumníku Windows otevřete rozbalenou složku `verka-portfolio`, označte **celý její obsah**
   (Ctrl+A – včetně složek `.github`, `data`, `scripts`) a přetáhněte ho do okna prohlížeče.
   Nepřetahujte samotnou složku `verka-portfolio`, ale to, co je v ní.
3. Zkontrolujte, že se v seznamu objevil i soubor `.github/workflows/update.yml`.
4. Dole **Commit changes**.

> Kdyby se složka `.github` nenahrála: v repozitáři **Add file → Create new file**, jako název napište
> `.github/workflows/update.yml` (lomítka vytvoří složky), vložte obsah souboru a uložte.

### 4. Zapnutí GitHub Pages
1. V repozitáři **Settings** → v levém menu **Pages**.
2. **Build and deployment → Source:** vyberte **GitHub Actions**. Nic jiného tam nenastavujte.

### 5. První spuštění
Hned po nahrání souborů se workflow spustí samo a nejspíš skončí červeně, protože Pages ještě nebyly zapnuté.
To nevadí – po kroku 4 ho spusťte ručně:

1. Záložka **Actions**. Pokud se objeví tlačítko *I understand my workflows, go ahead and enable them*, klikněte na něj.
2. Vlevo vyberte **Aktualizace cen a nasazení webu** → vpravo **Run workflow** → **Run workflow**.
3. Po minutě až dvou se běh zezelená. Kliknutím na něj a na krok **Stažení cen a výpočet portfolia** uvidíte,
   co se stáhlo – u každého fondu řádek typu `invesco-ai: +1 nových cen, poslední 2026-11-13`.
   Žlutá varování `stažení selhalo` znamenají, že se ceny toho fondu stáhnout nepodařilo (viz *Problémy*).
4. Adresa webu je v **Settings → Pages** nahoře a má tvar `https://VAŠE-JMÉNO.github.io/investice/`.

Od té chvíle se workflow spouští samo každý den kolem 7:30 ráno (GitHub plánované běhy občas o pár desítek minut zpozdí)
a také pokaždé, když v repozitáři změníte nákupy, seznam fondů nebo stránku.

---

## Běžná údržba

### Nový nákup
1. V repozitáři otevřete `data/nakupy.csv` → ikona tužky (**Edit**).
2. Přidejte řádek, např.:
   ```
   2026-12-05,Conseq realitní (CZK),48000,100000
   ```
   Sloupce: `datum` (RRRR-MM-DD), `fond` (název přesně jako ve `funds.json` nebo v jeho `aliases`),
   `pocet_kusu` (desetinná **tečka**), `castka_czk` (kolik se skutečně zaplatilo, včetně poplatků).
3. **Commit changes**. Web se do pár minut přepočítá sám.

`castka_czk` je nepovinná. Když chybí, spočítá se jako počet kusů × cena podílového listu k datu nákupu.
To nezahrnuje vstupní poplatek, takže zisk pak vychází o poplatek vyšší. Pokud znáte skutečně zaplacené částky,
doplňte je i ke stávajícím řádkům.

### Nový fond
Do `funds.json` přidejte položku. `productid` je číslo z adresy
`https://www.conseq.cz/Conseq/Pricehist.ashx?productid=…` (u stažených souborů bylo i na konci názvu,
např. `…CZ0008472859_10.xlsx` → `10`). `id` je libovolný krátký název bez mezer a diakritiky.

---

## Soukromí
Veřejný repozitář znamená, že **kdokoli, kdo zná adresu, uvidí stránku i soubor s nákupy**
(počty kusů a částky). Stránka má značku `noindex`, takže by ji vyhledávače neměly zobrazovat, ale tajná není.
Pokud vám to vadí, existují dvě cesty:
- **GitHub Pro** (placený) umožní Pages ze soukromého repozitáře – stránka je pak ale pořád veřejná, skryje se jen repozitář;
- nebo upravit web tak, aby ukazoval jen procenta místo korun (stačí napsat).

## Problémy
- **Stažení cen selže u všech fondů** – Conseq možná blokuje servery GitHubu nebo změnil formát souboru.
  Web dál ukazuje poslední uložené ceny. V logu běhu je důvod (např. `HTTP Error 403`).
- **Červený běh s hláškou o oprávnění při `git push`** – Settings → Actions → General → *Workflow permissions* →
  **Read and write permissions** → Save, a spusťte znovu.
- **Červený krok `deploy-pages`** – zkontrolujte, že v Settings → Pages je zdroj **GitHub Actions** (krok 4).
- **Plánované běhy přestaly** – GitHub vypíná plánované workflow ve veřejných repozitářích po 60 dnech bez aktivity;
  v Actions je pak tlačítko pro opětovné zapnutí.

## Spuštění u sebe (nepovinné)
```
pip install -r requirements.txt
python scripts/update.py            # stáhne ceny a přepočítá
python scripts/update.py --no-download
python -m http.server               # pak otevřít http://localhost:8000
```
