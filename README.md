# Reolink SIP Gateway – Home-Assistant-Integration

Diese benutzerdefinierte Integration bindet die lokale API der **Reolink SIP
Gateway App** in Home Assistant ein. Sie zeigt Anrufzustand und anrufende Nummer
an und stellt die beiden vereinbarten Bedienelemente **Testanruf** und
**Auflegen** bereit.

> Community-Projekt: Dieses Repository ist weder mit Reolink noch mit dem
> Home-Assistant-Projekt verbunden und wird von diesen nicht unterstützt.

## Voraussetzungen

- Reolink SIP Gateway App **0.9.0 oder neuer**
- Home Assistant **2025.1 oder neuer**
- Netzwerkzugriff von Home Assistant auf die lokale Gateway-API
- API-Adresse und Zugriffstoken von der Ingress-Seite der App

Die Integration verändert keine SIP-, Audio- oder Reolink-Konfiguration. Sie
nutzt ausschließlich den versionierten Vertrag unter `/api/v1`.

## Entitäten

Alle vier Entitäten gehören zu einem Gerät mit der dauerhaften Installations-ID
des Gateways:

| Entität | Aufgabe |
| --- | --- |
| `sensor.reolink_sip_gateway_status` | Zustände `bereit`, `eingehend`, `ausgehend`, `verbunden`, `fehler` |
| `sensor.reolink_sip_gateway_anrufende_nummer` | Aktuelle oder zuletzt angenommene eingehende Nummer |
| `button.reolink_sip_gateway_testanruf` | Ruft das in der App konfigurierte SIP-Ziel an |
| `button.reolink_sip_gateway_auflegen` | Beendet den aktiven ein- oder ausgehenden Anruf |

Der Statussensor führt außerdem SIP-Registrierung, Anrufrichtung, laufende bzw.
letzte Anrufdauer, Codec und letzte eingehende Nummer als Attribute. Die
Auflegen-Schaltfläche ist nur während eines Anrufs verfügbar; der Testanruf nur,
wenn das Gateway den Befehl annehmen kann.

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

1. Die Reolink SIP Gateway App 0.9.0 starten.
2. Ihre Ingress-Seite öffnen und **API-Adresse** sowie **Token** kopieren.
3. In Home Assistant **Einstellungen → Geräte & Dienste → Integration
   hinzufügen** öffnen.
4. **Reolink SIP Gateway** auswählen und beide Werte eintragen.

Die Integration prüft API-Version, Fähigkeiten und die dauerhafte
Installations-ID, bevor sie den Eintrag anlegt. Eine automatische
Supervisor-Erkennung ist in der ersten Version bewusst nicht enthalten.

## Aktualisierung und Ausfallsicherheit

Statusänderungen werden über Server-Sent Events unmittelbar übertragen. Nach
einem Verbindungsabbruch verbindet sich die Integration mit begrenztem Backoff
neu. Ein vollständiger Abruf von `/status` alle 60 Sekunden dient zusätzlich als
Abgleich und Fallback. Langsame oder unterbrochene Ereignisverbindungen greifen
nicht in die Echtzeit-Audioverarbeitung des Gateways ein.

## Sicherheit

- Jeder API-Aufruf verwendet das 256-Bit-Bearer-Token der App.
- Das Token erscheint weder in Entitätsattributen noch in Protokollmeldungen.
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
