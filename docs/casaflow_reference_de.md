# CasaFlow-Referenz

CasaFlow ist eine private App für Immobilienfinanzen. Sie verwaltet die finanzielle Sicht auf deinen Eigentumsanteil an einem Immobilienportfolio und hält Immobilien, Einheiten, Mieterhistorie, Darlehen, Deals und bankfähige Exporte an einem Ort zusammen.

Die wichtigste Logik: Die finanzielle Analyse findet im Dashboard und auf der Darlehensseite statt. Immobilien- und Einheiten-Seiten dienen der sauberen Pflege der Quelldaten.

## Workflow-Mindmap

Die App zeigt hier eine visuelle CasaFlow-Bereiche-Mindmap. Sie teilt CasaFlow in Portfolio-Verwaltung, Portfolio-Analyse und Portfolio-Entscheidungen.

## Datenstruktur

- Immobilie: ein zusammengefasstes Immobilienobjekt. Ein Haus mit mehreren Wohnungen ist eine Immobilie.
- Einheit: eine Wohnung oder vermietbare Einheit unterhalb einer Immobilie.
- Mieter / Person: ein wiederverwendbarer Personendatensatz.
- Mietverhältnis: der Zeitraum, in dem eine Mietergruppe eine Einheit mietet.
- Mietperiode: die Miete, die ab einem bestimmten Datum innerhalb eines Mietverhältnisses gilt.
- Darlehen: der Finanzierungsvertrag für eine Immobilie.
- Jährliche Darlehensdaten: jährliche Schlusssalden zur Berechnung von Schuld, Zinsen, Tilgung und Kapitaldienst.
- Jährliche Immobiliendaten: Werte, Leerstand/Verlust und nicht umlagefähige Kosten.
- Deal: eine mögliche zukünftige Immobilie, die noch nicht Teil des echten Portfolios ist.
- Finanzierungsszenario: eine mögliche Darlehens-/Eigenkapitalstruktur für einen Deal.

## Namenskonventionen

- Cashflow bedeutet das Immobilienergebnis nach Betriebskosten, Leerstand/Verlust, Zinsen und, bei Portfolio-Kennzahlen im Dashboard, nach dem gewählten Steuermodus.
- Freier Cashflow bedeutet Liquidität nach vollständiger Darlehenszahlung und gewähltem Steuermodus.
- Eigenkapitalaufbau bedeutet Schuldenreduktion durch Tilgung.
- Dein investiertes Eigenkapital ist das tatsächlich von dir eingebrachte Eigenkapital. Bankfinanzierte Beträge zählen nicht dazu.
- Jährlicher Eigentümer-ROI bedeutet jährliche Eigentümerrendite im Verhältnis zu deinem investierten Eigenkapital.
- Effektiver Zinssatz ist der tatsächlich gezahlte Zins im Verhältnis zum relevanten Darlehenssaldo.
- LTV bedeutet Loan-to-Value im Immobiliensinn.
- Kaltmiete enthält keine Nebenkosten und keine Mietervorauszahlungen.
- Betriebskosten sind in CasaFlow nicht umlagefähige Kosten, also Kosten, die Mieter nicht zurückzahlen.
- Zeigt deinen Anteil bedeutet, dass Beträge mit dem jeweiligen Eigentumsanteil multipliziert werden.
- Zeigt Gesamtobjektwerte bedeutet, dass Beträge als Gesamtwerte der Immobilie vor Eigentumsanteil angezeigt werden.

## Kernformeln

```text
Cashflow = Kaltmiete - Betriebskosten - Leerstand/Verlust - Zinsen
Steuerliches Portfolio-Ergebnis = Portfolio-Cashflow vor Steuern - jährliche steuerlich absetzbare Kosten
Cashflow nach Steuern = Portfolio-Cashflow vor Steuern - geschätzte Steuer
Freier Cashflow = Cashflow - Tilgung
Eigenkapitalaufbau = Tilgung
Total Value Added = Freier Cashflow + Eigenkapitalaufbau + unrealisierter Wertzuwachs
Jährlicher Eigentümer-ROI = Cashflow / dein investiertes Eigenkapital
NOI = Kaltmiete - Leerstand/Verlust - Betriebskosten
LTV = Schuld / Immobilienwert
Nettorendite = NOI / Immobilienwert
Bruttorendite = Kaltmiete / Immobilienwert
Kapitaldienst = Zinsen + Tilgung
DSCR = NOI / Kapitaldienst
```

## Formelprinzipien

- Tilgung wird nicht als Kostenposition im Cashflow behandelt, weil sie durch Schuldenreduktion zu Eigenkapital wird.
- Freier Cashflow zeigt die echte Liquidität nach vollständiger Darlehenszahlung.
- Eigenkapitalaufbau wird separat gezeigt, damit Liquidität und Vermögensaufbau getrennt sichtbar bleiben.
- Unrealisierter Wertzuwachs ist kein Teil des Cashflows, weil er erst bei Verkauf oder Refinanzierung zu realem Geld wird.
- Total Value Added ist ein weiter gefasstes Zukunftskonzept, das unrealisierte Wertsteigerung enthalten kann.
- Dashboard-Werte nutzen den Eigentumsanteil.
- Bankexporte nutzen Gesamtobjektwerte und zeigen den Eigentumsanteil separat.

## Vor-Steuer- und Nach-Steuer-Modus

Die Steuerberechnung kann in den Einstellungen aktiviert oder deaktiviert werden. Wenn sie deaktiviert ist, werden alle Steuer-Elemente ausgeblendet und das Dashboard zeigt Werte vor Steuern. Wenn sie aktiviert ist, hat das Dashboard einen Vor-Steuer-/Nach-Steuer-Schalter, wobei Nach Steuern die Standardansicht ist.

- Vor Steuern nutzt die Kernformel: Cashflow = Kaltmiete - Betriebskosten - Leerstand/Verlust - Zinsen.
- Nach Steuern zieht eine geschätzte Portfolio-Steuer vom Portfolio-Cashflow ab.
- Jährliche steuerlich absetzbare Kosten werden einmal pro Jahr in den Einstellungen gepflegt. Sie sind steuerliche Abzüge und reduzieren nicht den Cashflow vor Steuern, außer sie wurden an anderer Stelle bereits als Kosten erfasst.
- Wenn das steuerliche Ergebnis negativ ist und Steuervorteile bei Verlusten aktiviert sind, behandelt CasaFlow die negative Steuer als geschätzten Vorteil.
- Steuer wird einmal für den ausgewählten Portfolio-Umfang berechnet, nicht getrennt pro Immobilie.
- NOI, Bruttorendite, Nettorendite, LTV, DSCR, Schuld, Kapitaldienst, Eigenkapital, Eigenkapitalaufbau und Immobilienwert bleiben steuerunabhängig.

## Dashboard-Kennzahlen

- Cashflow: wichtigste Rentabilitätskennzahl für das ausgewählte Jahr. Portfolio-Summen folgen dem Steuermodus.
- Freier Cashflow: Liquidität nach Tilgung. Portfolio-Summen folgen dem Steuermodus.
- Eigenkapitalaufbau: Schuldenreduktion durch Tilgung.
- Jährlicher Eigentümer-ROI: ausgewählter Portfolio-Cashflow geteilt durch dein investiertes Eigenkapital.
- Kumulativer Eigentümer-ROI: kumulierter ausgewählter Portfolio-Cashflow geteilt durch dein investiertes Eigenkapital.
- Portfoliowert: Immobilienbewertungen multipliziert mit dem Eigentumsanteil.
- Gesamtschuld: Darlehenssalden multipliziert mit dem Eigentumsanteil.
- LTV: Gesamtschuld geteilt durch Portfoliowert.

## Darlehens-Kennzahlen

- Aktuelle Schuld: aktueller oder angenäherter Darlehenssaldo multipliziert mit dem Eigentumsanteil.
- Effektiver Zinssatz: gezahlte Zinsen geteilt durch Anfangsschuld.
- Zinskosten: jährliche Zinsen multipliziert mit dem Eigentumsanteil.
- Tilgung: jährliche Schuldenreduktion multipliziert mit dem Eigentumsanteil.
- Kapitaldienst: Zinsen plus Tilgung.
- Tilgungsquote: Tilgung geteilt durch Anfangsschuld.

## Deal-Kennzahlen

Deals verwenden Eingaben als Gesamtobjektwerte, zeigen Entscheidungs-KPIs aber für deinen Eigentumsanteil.

- Cashflow = erwartete anteilige Kaltmiete - anteilige Betriebskosten - anteilige Zinskosten.
- Freier Cashflow = Cashflow - geschätzte Tilgung.
- Eigenkapitalaufbau = geschätzte Tilgung.
- Jährlicher Eigentümer-ROI = Cashflow / dein investiertes Eigenkapital.
- Dein investiertes Eigenkapital gehört zu jedem Finanzierungsszenario, nicht zum Deal selbst.
- Finanzierungsszenarien sollten nach Rendite, Liquidität, zusätzlicher Schuld und erforderlichem Eigenkapital verglichen werden.

## Exporte

Die Bank-Finanzierungsübersicht ist für Darlehensanfragen und Bankkommunikation gedacht.

- Immobilienwerte sind Gesamtobjektwerte.
- Darlehensbeträge sind Gesamtobjektwerte.
- Der Eigentumsanteil wird separat ausgewiesen.
- Jährliche Kaltmiete basiert auf der aktuell erwarteten Kaltmiete.
- Der aktuelle Darlehensbetrag nutzt die besten verfügbaren jährlichen Darlehensdaten.

## Aktuelle Nicht-Ziele

- CasaFlow verfolgt keine tatsächlichen Mietzahlungen.
- CasaFlow nutzt eine einfache Dashboard-Steuerschätzung, keine formale Steuerbuchhaltung.
- CasaFlow enthält keinen unrealisierten Wertzuwachs im Cashflow.
- CasaFlow ersetzt keine formale Buchhaltung und keine Steuerberatung.
- Deals sind Planungsdatensätze und beeinflussen das echte Portfolio erst nach einer späteren manuellen Umwandlung.
