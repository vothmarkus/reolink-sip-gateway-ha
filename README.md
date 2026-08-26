# Reolink SIP Gateway – Home-Assistant-Integration

Diese benutzerdefinierte Integration bindet die lokale API der **Reolink SIP
Gateway App** in Home Assistant ein. Sie zeigt Anrufzustand, anrufende Nummer
und die aktuelle beziehungsweise letzte Route an. Mit Gateway 1.2 stellt sie
für jede vorhandene Anrufroute einen eigenen **Testanruf**-Button sowie einmal
**Auflegen** bereit. Ab Version 1.0 übergibt sie empfangene DTMF-Tastendrücke als
reine Home-Assistant-Ereignisse an Automationen.

> Community-Projekt: Dieses Repository ist weder mit Reolink noch mit dem
> Home-Assistant-Projekt verbunden und wird von diesen nicht unterstützt.

## Voraussetzungen

- Reolink SIP Gateway App **1.0.0 oder neuer**; für Routenkatalog und mehrere
  Testanruf-Buttons **1.2.0 oder neuer**
- Home Assistant **2025.1 oder neuer**
- Netzwerkzugriff von Home Assistant auf die lokale Gateway-API
- Add-on-Hostname und Zugriffstoken von der Ingress-Seite der App

Die Integration verändert keine SIP-, Audio- oder Reolink-Konfiguration. Sie
nutzt ausschließlich den versionierten Vertrag unter `/api/v1`.

## Entitäten

Alle Entitäten gehören zu einem Gerät mit der dauerhaften Installations-ID des
Gateways:

| Entität | Aufgabe |
| --- | --- |
| `sensor.reolink_sip_gateway_status` | Zustände `bereit`, `eingehend`, `ausgehend`, `verbunden`, `fehler` |
| `sensor.reolink_sip_gateway_anrufende_nummer` | Aktuelle oder zuletzt angenommene eingehende Nummer |
| `button.reolink_sip_gateway_testanruf_<route>` | Je ein Button pro Gateway-Route; ruft ausschließlich deren Tür-/Mobilziele an |
| `button.reolink_sip_gateway_auflegen` | Beendet den aktiven ein- oder ausgehenden Anruf |

Der Statussensor führt außerdem SIP-Registrierung, Anrufrichtung, laufende bzw.
letzte Anrufdauer, Codec, aktuelle/letzte Routen-ID, Routennamen und letzte
eingehende Nummer als Attribute. Die Auflegen-Schaltfläche ist nur während
eines Anrufs verfügbar; jeder Testanruf nur, wenn mindestens ein von seiner
Route verwendeter SIP-Weg registriert und der globale Anrufplatz frei ist.

Die stabile Routen-ID bestimmt die dauerhafte Unique-ID des Testanruf-Buttons;
der sichtbare Name stammt aus der App-Konfiguration. Neu hinzugefügte Routen
erscheinen nach dem nächsten Statusupdate automatisch. Wird eine Route entfernt,
bleibt eine bereits registrierte Entity sicherheitshalber unverfügbar, statt
versehentlich eine andere Route anzurufen. Bei Gateways vor 1.2 bleibt der eine
kompatible allgemeine Testanruf-Button erhalten.

## DTMF-Ereignis

Für jeden vollständig empfangenen RFC-4733-Tastendruck löst die Integration
genau dieses Home-Assistant-Ereignis aus:

`reolink_sip_gateway_dtmf`

Seine Schnittstelle besteht ausschließlich aus folgenden Ereignisdaten:

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `digit` | String | `0`–`9`, `*`, `#` oder `A`–`D` |
| `duration_ms` | Integer | vom SIP-Endgerät gemeldete Tastendauer in Millisekunden |
| `call_direction` | String | `incoming` oder `outgoing` |
| `remote_number` | String | exakt normalisierte Gegenstelle: eingehender Anrufer oder konfiguriertes ausgehendes SIP-Ziel |
| `call_id` | String | SIP-Dialog-ID zur sicheren Trennung mehrerer Anrufe |
| `received_at` | String | Empfangszeitpunkt mit Zeitzone im ISO-8601-Format |
| `instance_id` | String | dauerhafte Installations-ID des Gateways |

Die Integration legt dafür keine Entity an und führt weder Ziffernfolgen noch
PINs oder Aktionen aus. Die gesamte Bedeutung bleibt in der Home-Assistant-
Automation. Beispiel für die Taste `5`:

```yaml
triggers:
  - trigger: event
    event_type: reolink_sip_gateway_dtmf
    event_data:
      digit: "5"
actions:
  - action: light.turn_on
    target:
      entity_id: light.flur
```

Für mehrere mehrstellige Codes, eine Bestätigung mit `#` und Rufnummernregeln
pro Code kann die separate Integration
[`DTMF Code`](https://github.com/vothmarkus/DTMF-Code-HA) dieses Rohereignis
auswerten und pro Codeprofil eine eigene Ereignis-Entität bereitstellen.

Nur ausgehandeltes Out-of-Band-DTMF (`telephone-event/8000`) wird erkannt;
hörbare Töne im Audiosignal werden nicht ausgewertet. Das Ereignis ist bewusst
flüchtig und wird nach einer unterbrochenen SSE-Verbindung nicht nachträglich
wiederholt.

## Installation über HACS

1. In HACS **Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/vothmarkus/reolink-sip-gateway-ha` als Typ
   **Integration** hinzufügen.
3. **Reolink SIP Gateway** installieren.
4. Home Assistant neu starten.

Alternativ kann der Ordner
`custom_components/reolink_sip_gateway` manuell in den gleichnamigen Ordner der
Home-Assistant-Konfiguration kopiert werden.

## Einrichtung

1. Die Reolink SIP Gateway App starten; für routenspezifische Buttons mindestens 1.2.0.
2. Ihre Ingress-Seite öffnen und **Add-on-Hostname** sowie **Token** kopieren.
3. In Home Assistant **Einstellungen → Geräte & Dienste → Integration
   hinzufügen** öffnen.
4. **Reolink SIP Gateway** auswählen und beide Werte eintragen. Aus dem
   Hostnamen erzeugt die Integration intern automatisch
   `http://<Hostname>:18099/api/v1`.

Die Integration prüft API-Version, Fähigkeiten und die dauerhafte
Installations-ID, bevor sie den Eintrag anlegt. Eine automatische
Supervisor-Erkennung ist in der ersten Version bewusst nicht enthalten.

## Aktualisierung und Ausfallsicherheit

Statusänderungen und DTMF werden über Server-Sent Events unmittelbar übertragen. Nach
einem Verbindungsabbruch verbindet sich die Integration mit begrenztem Backoff
neu. Ein vollständiger Abruf von `/status` alle 60 Sekunden dient zusätzlich als
Abgleich und Fallback. Langsame oder unterbrochene Ereignisverbindungen greifen
nicht in die Echtzeit-Audioverarbeitung des Gateways ein. Status ist
rekonstruierbar; ein während der Unterbrechung empfangener Tastendruck dagegen
absichtlich nicht.

## Sicherheit

- Jeder API-Aufruf verwendet das 256-Bit-Bearer-Token der App.
- Das Token erscheint weder in Entitätsattributen noch in Protokollmeldungen.
- Empfangene DTMF-Ziffern können in Home-Assistant-Automationsspuren erscheinen;
  Zugangscodes deshalb wie andere Geheimnisse behandeln.
- Die App akzeptiert API-Verbindungen ausschließlich aus privaten, lokalen oder
  Link-Local-Netzen.
- Bei geändertem Token startet Home Assistant einen Ablauf zur erneuten
  Authentifizierung.

## Entwicklung

```bash
python -m pip install -r requirements_test.txt
ruff check .
ruff format --check .
pytest -q
```

GitHub Actions prüft zusätzlich die Home-Assistant-Struktur mit Hassfest und die
HACS-Kompatibilität.
